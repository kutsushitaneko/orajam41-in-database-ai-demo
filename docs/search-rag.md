# ベクトル検索とRAGの実行手順

[共通データの投入](demo-data.md)を終えたら、文書をベクトル化して検索とRAGを試します。以下のコマンドはすべてプロジェクトのルートから実行します。

## 事前に16件をベクトル化する

```powershell
uv run --locked python -m webinar_demo.search --prepare
```

DB内のMULTILINGUAL_E5_LARGEで、タイトルと本文を結合した16件の断片を1024次元へ変換します。このモデルの仕様に従い、文書には`passage: `、質問には`query: `を付けます。詳細は下のモデルカードを参照してください。質問のベクトルもDB内で生成するため、埋め込み用の外部APIやローカルのPyTorchは不要です。

SQLクライアントでは`sql/setup/50_embed_documents.sql`のブロック全体を実行します。既存ベクトルは、記録されたモデル名が一致すれば保持します。本文や前処理の変更はデータの再投入処理でベクトルをNULLに戻すため、再度`--prepare`を実行します。同じDBモデル名でONNXを置き換える場合は、別途ベクトルを無効化して全件再生成する必要があります。モデル名だけで重みの更新を検出する仕組みではありません。

初回の16件生成は今回の環境で16.581秒でした。検索を始める前に完了させてください。モデルは最大512トークンに切り詰める仕様があるため、今回は短い固定文書を使っています。長文へ拡張する際は、文字数だけで長さを判断せず、トークン単位で分割する処理を追加してください。[モデルカード](https://huggingface.co/intfloat/multilingual-e5-large)

## デモA：意味・機種・キーワードを組み合わせる

### 言い換えで探す

```powershell
uv run --locked python -m webinar_demo.search --case-id SR001 --question '管理画面が固まって操作できない' --model AX-100
uv run --locked python -m webinar_demo.search --case-id SR001 --question '管理画面が固まって操作できない' --model AX-100 --mode keyword --keyword '固まって'
```

意味検索はKB001「管理画面が応答しないとき」を1位に返します。同じ語句の部分一致検索は0件です。本文にない言い換えでも意味検索で候補を探せることを示します。

ベクトル列は1モデルに統一し、モデル名は検索フィルターに使いません。embedding_modelは生成履歴と再生成確認用です。

検索は`OJ41_VISIBLE_CHUNKS`を対象とする厳密検索です。COSINE距離は小さいほど近く、同距離の場合は文書IDで順序を固定します。小規模デモなので近似索引は作成していません。距離が表すのはベクトルの近さです。回答の正しさの判断には、別途評価が必要です。[VECTOR_DISTANCE](https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/vector_distance.html)

### 機種を限定する

```powershell
uv run --locked python -m webinar_demo.search --case-id SR001 --question 'E101の対処は？'
uv run --locked python -m webinar_demo.search --case-id SR001 --question 'AX-100のE101の対処は？' --model AX-100
uv run --locked python -m webinar_demo.search --case-id SR001 --question 'BX-200のE101の対処は？' --model BX-200
```

機種条件を付けない検索では、AX-100の温度警告KB002とBX-200の認証設定KB006が混在します。機種の一致は意味の近さとは別の条件です。`--device DEV001`を指定すると、閲覧可能な機器表からAX-100を取得します。機器と指定機種が一致しない場合は停止します。

### 補足：本編では扱わないキーワード併用

```powershell
uv run --locked python -m webinar_demo.search --case-id SR001 --question '電源の警告が出た' --model AX-100 --mode hybrid --keyword E201
```

このデモの`hybrid`は、キーワードを含む文書を先に並べ、その中をベクトル距離で並べる簡単な実装です。KB003が1位になります。`keyword`は`INSTR`による部分一致で、Oracle Textの全文検索やハイブリッド・ベクトル索引は使用しません。必要に応じて試せる補助機能です。

SQLクライアントでは`sql/demos/01_vector_search.sql`を開き、A0〜A3のSELECTを順に実行します。Python版は質問ベクトルを一度取得してバインドし、SQL版は`VECTOR_EMBEDDING`をSELECT内に記述して処理を見える形にしています。

## デモB：検索した文書から回答する

```powershell
uv run --locked python -m webinar_demo.rag --case-id SR001 --question 'DEV001の管理画面が開かない。最初に何を確認する？'
uv run --locked python -m webinar_demo.rag --case-id SR001 --question 'AX-100のE101の対処は？'
```

処理は、閲覧範囲と機種を確認し、DBで文書を検索し、質問・確認した機種・取得した文書をOCI GenAIへ送る順です。Pythonからの呼び出しには.envのAPI署名キーを使います。モデルはxai.grok-4.3、リージョンはus-chicago-1です。今回のRAGはローカルPythonからGenAIへ接続するため、DBのリソースプリンシパルはこのLLM呼び出しには使いません。

LLMへの送信対象は質問、対象機種、最大3件の文書IDと本文です。東京のDBから取り出した情報をChicagoのLLMへ送る構成になります。パスワードやOCIの接続設定をプロンプトへ含めません。

回答は、説明・文書ID・原文引用を組にしたJSONで表示します。今回の実測例は次のとおりです。

| 質問 | 回答の内容 | 根拠 |
|---|---|---|
| DEV001の画面が開かない | まず電源ランプとLANケーブルを確認 | KB001の該当文を引用 |
| AX-100のE101 | 吸気口と室温を確認し、温度・時刻を記録。分解せず、警告が続けば保守窓口へ連絡 | KB002の各手順を引用 |

コードは、引用IDが取得文書に存在することと、引用文が原文に含まれることを検査します。不正なJSONや引用なら回答を表示せず停止します。ただし、原文の引用が正しくても説明の意味が原文と一致するとは限りません。今回の2回答は説明と引用を目視でも照合しました。任意の質問に対する忠実性を保証する仕組みではありません。

## 根拠不足は検索と生成で分けて確認する

```powershell
uv run --locked python -m webinar_demo.rag --case-id SR001 --question 'AX-100のE999の修理方法は？'
uv run --locked python -m webinar_demo.rag --case-id SR001 --question 'AX-100の保証延長料金を日本円で教えて。'
```

E999は文書に存在しません。RAGでは質問中のE＋3桁のコードを追加の必須条件とし、候補が0件ならLLMを呼ばずに根拠不足を返します。エラーコードの条件を付けない一般の意味検索とは、この点が異なります。

保証延長料金の質問では関連しそうな文書が検索されますが、料金の記載はありません。この場合はLLMに判断させ、今回の検証では`insufficient`と空のclaimsが返りました。検索で0件になるケースと、取得した資料が質問に答えられないケースの両方を示します。

SR001の処理中に別顧客C002や、チケットの範囲外のDEV009を指定した質問は、LLM呼び出し前に停止します。すべての検索は、選択中のチケットの顧客で絞るビューを使います。`--case-id SR002`で担当者がチケットを切り替えればDEV009を照会できます。顧客IDの文字列検査だけをアクセス制御の根拠にはしません。所有者スキーマ内で実演することの制約は[共通データの手順](demo-data.md)を参照してください。契約判断と訪問手配案は[NL2SQL・Agentの手順](nl2sql-agent.md)で扱います。

## 評価を実行する

```powershell
# ローカルの回答形式・引用検査。外部接続なし。
uv run --locked pytest -q --basetemp=local/pytest-stage3

# 実DBの検索10ケース。GenAI呼び出しなし。
uv run --locked python -m webinar_demo.evaluate_stage3

# 検索10ケース＋RAG6ケース。GenAIは最大3回呼び出す。
uv run --locked python -m webinar_demo.evaluate_stage3 --rag
```

実行結果はGit管理外の`local/stage3-evaluation.json`へ順次保存します。途中で失敗した場合、このファイルは途中経過であり、全ケース成功とは扱いません。LLMはtemperature=0でも出力や時間が変わり得ます。評価では期待文書、回答状態、引用との対応を確認し、文章の完全一致は求めません。


モデル名の不一致や未生成ベクトルがある場合は、検索が停止します。データの再投入後は`--prepare`を実行してください。引用検証で停止した場合は、未検証の回答を採用せず、質問・取得文書・実行条件を確認します。通信エラーはネットワーク制約と認証を切り分けて調査してください。
