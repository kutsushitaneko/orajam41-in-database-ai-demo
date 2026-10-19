# NL2SQL：参照範囲の制限とANNOTATIONの検証

2026年10月19日、Autonomous AI Database 26aiの既存デモ環境で実測した。SQL生成モデルはOCI Generative AIの`xai.grok-4.3`（us-chicago-1）、temperature=0、max_tokens=1600。データと契約の固定基準日は既存教材のままで、モデルの再ロードやデータの再投入は行っていない。

## 採用する構成

BASELINEとTUNEDの両方で`object_list_mode=all`、`enforce_object_list=true`、`comments=false`を明示する。変更する属性は`annotations=false`と`true`だけ。ビューの説明1件と列の説明6件を`description`注釈として登録する。

実DBのOJ41表・ビュー14個を確認し、次の6個を参照対象とした。

| 対象 | 理由 |
|---|---|
| OJ41_VISIBLE_CONTRACTS | チケットの顧客の契約と判定済み列 |
| OJ41_VISIBLE_DEVICES | チケットの顧客のサーバー |
| OJ41_VISIBLE_KNOWLEDGE | 公開範囲を適用した文書 |
| OJ41_VISIBLE_CHUNKS | 公開範囲を適用した文書チャンク |
| OJ41_RUN | 教材の固定基準日 |
| OJ41_BULK_PARTS | ロード進捗。制限対象の本文を含まない |

顧客・チケット・サーバー・契約・文書・チャンクのベース表6個は、閲覧用ビューの制限を迂回するため除外した。OJ41_BULK_DOCSとOJ41_BULK_STAGEも、顧客専用・内部向け文書を複製するため除外した。契約の正解を返すビューだけに候補を絞った構成ではない。

大量ロードを準備していない環境ではOJ41_BULK_PARTSを除く5個になる。準備コードは存在するオブジェクトを確認し、未分類のOJ41表・ビューがあれば停止する。5個構成の分岐は単体テストで確認したが、以下の生成結果は6個構成の実測である。

## 調整と結果

初めに、従来のコメントと同じ内容をANNOTATIONへ移した。主質問、機種別件数、無効契約、SR002の主質問は各3回成功したが、「DEV009の機器IDと契約ID」は3回失敗した。機種列との取り違え、またはPython検証器が許可しない不要なJOINが原因だった。

そこでDEVICE_IDがメーカー発行の保守登録番号で、MODELやSERIAL_NOとは異なることを明示し、CONTRACT_IDにも説明を追加した。質問文や参照対象は変更していない。調整後の予備検証15回に続き、教材の正式な準備処理でプロファイルを作り直して次を確認した。

| 条件／質問 | 回数 | 結果 |
|---|---:|---|
| 注釈なし：SR001の現地保守対象 | 3 | 3回ともSQLを生成できないという応答。実行していない |
| 注釈あり：SR001の現地保守対象 | 3 | 3回ともDEV001・DEV005・DEV006・DEV008 |
| 注釈あり：機種別の対象台数 | 3 | 3回ともAX-100は3台、BX-200は1台 |
| 注釈あり：別顧客DEV009 | 3 | 3回とも正しいDEVICE_ID条件で0件 |
| 注釈あり：無効な契約 | 3 | 3回ともDEV002・DEV003・DEV007 |
| 注釈あり：SR002の現地保守対象 | 3 | 3回ともDEV009 |

補助比較ではコメントあり・注釈なしも主質問3回に成功した。今回の結果はANNOTATIONがCOMMENTより優秀であることを示す比較ではなく、注釈で同じ用途を担えることを確認したもの。

制限対象のOJ41_CUSTOMERS、OJ41_CONTRACTS、OJ41_BULK_DOCSを直接参照するよう求めた3つの追加質問では、いずれもSQLを生成できない応答だった。これらの応答は表示だけとし、実行していない。生成・検証のどの内部段階で止まったかまでは、この応答だけから断定できない。

チケット未選択時は4つの閲覧用ビューがすべて0件。別顧客の番号の拒否、チケット切替、例外後の消去、独立したDB接続間のセッション分離も確認した。準備処理の再実行で注釈は7件に保たれ、契約ツール9ケース、ID差し替え拒否、呼び出し上限も確認した。無効状態のOJ41オブジェクトはなかった。ローカルテストは79件成功、実DBを必要とする別の5件はスキップした。

## 再実行

```powershell
uv run --locked python -m webinar_demo.evaluate_nl2sql_annotations --setup --repeats 3
uv run --locked python -m webinar_demo.evaluate_cases
```

結果は`local/nl2sql-annotations-evaluation.json`と`local/case-evaluation.json`に保存する。前者の`completed`、`all_tuned_match`、`unselected_empty`を確認する。SQLクライアントでは`sql/demos/02_nl2sql.sql`を同一接続でスクリプト実行し、C1とC2を記録する。C1は表示のみとし、C2は参照先と条件を確認したうえで、実行結果を正解SQLと照合する。

LLMの出力には変動があり、temperature=0も同一出力の保証ではない。参照制限は顧客範囲を適用したビューへの経路を守るための設定で、所有者ユーザーのDB権限そのものや、質問の意味の正しさを保証するものではない。Python検証器は、広めのメタデータ候補とは別に、実行を契約ビュー単独のSELECTへ限定している。

参照：[AIプロファイル属性](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/dbms-cloud-ai-package.html)、[注釈によるSQL生成の改善](https://docs.oracle.com/en/database/oracle/oracle-database/26/selai/generate-and-improve-sql-queries.html)、[ALTER VIEWの注釈構文](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/ALTER-VIEW.html)。
