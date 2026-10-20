# SQLクライアントで実行するデモ

本編はVS Code SQL Developerで実行します。埋め込み・検索・NL2SQLには既存のSQLを使い、RAGはDB内のPL/SQLで検索から回答検査まで処理します。LLMの推論はOCI Generative AIで行い、DBからリソースプリンシパルで呼び出します。

## 準備

既存の環境・データ・モデルの準備後、次のコマンドでAI定義とPL/SQLパッケージを登録します。既存プロファイルを再作成するため、デモ実行中には準備コマンドを実行しないでください。

```powershell
uv run --locked python -m webinar_demo.business_ai --setup
```

既にAI定義を登録済みの環境では、新しいパッケージだけをSQLクライアントで次の順に実行できます。モデルやデータの再投入は不要です。

1. [65_answer_guard.sql](../sql/setup/65_answer_guard.sql)
2. [66_answer_guard_body.sql](../sql/setup/66_answer_guard_body.sql)
3. [67_rag.sql](../sql/setup/67_rag.sql)
4. [68_rag_body.sql](../sql/setup/68_rag_body.sql)
5. [80_checked_agent.sql](../sql/setup/80_checked_agent.sql)
6. [81_checked_agent_body.sql](../sql/setup/81_checked_agent_body.sql)

RAGは`OJ41_BUSINESS_AI`を使用します。初回導入では[AI定義テンプレート](../sql/setup/64_business_ai_template.sql)または上記準備コマンドによる登録が必要です。新しいパッケージはすべてORAJAM41USERのスキーマ内に作成します。

## 実行順序

| 順序 | ファイル | 見る内容 |
|---|---|---|
| 基礎 | [00b_embedding_basics.sql](../sql/demos/00b_embedding_basics.sql) | DB内モデル、1024次元、全件紹介、近傍検索 |
| A | [01_vector_search.sql](../sql/demos/01_vector_search.sql) | チケットの顧客と機種による検索範囲の限定 |
| B | [01b_rag.sql](../sql/demos/01b_rag.sql) | 正常回答、検索候補なし、取得資料に答えなし |
| C | [02_nl2sql.sql](../sql/demos/02_nl2sql.sql) | ANNOTATIONの有無による生成SQLの比較 |
| D | [03_support_agent.sql](../sql/demos/03_support_agent.sql) | 回答、契約値、ツールの実行履歴を照合 |
| 参考 | [04_checked_agent.sql](../sql/demos/04_checked_agent.sql) | 自動検査した回答と対応方針。本編では実演しない |

DBMS Outputを有効にし、PL/SQLは`DECLARE`または`BEGIN`から`END;`までをまとめて実行します。RAGと自動検査Agentの関数はPL/SQLから呼び出してください。検索前のコンテキスト設定や外部サービス呼び出しを含むため、`SELECT 関数(...) FROM dual`への置き換えは想定していません。

`OJ41_RAG.answer_question`と`OJ41_CHECKED_AGENT.run`はチケットの開始と消去を管理します。外側で別のチケット処理を継続しているセッション内に入れ子で呼ばず、リクエスト単位で使用します。通常のA・C・Dは、各スクリプト内の開始・照会・消去まで同じ接続で実行します。

## 自動検査の範囲

RAGは質問長、保守登録番号・機種の矛盾、顧客範囲、複数のエラーコード、未生成・異なるモデルのベクトルを確認します。質問内の`DEV`＋3桁、`C`＋3桁、`E`＋3桁、英字2文字＋ハイフン＋3桁はデモ用の識別子として扱います。日本語に接していても抽出する保守的な実装です。候補0件なら生成を呼ばず、候補があればJSON形式、claims件数・型・長さ、取得文書ID、原文引用を検査します。

Agentの自動検査版は、両ツールが各1回呼ばれたこと、独自トレースのrun_idと標準履歴の一致、文書IDと引用、未承認の訪問確約を表す特定の文言を検査します。対応方針は生成文から推測せず、ツールが返した契約データから決めます。回答と契約結果の全体的な意味の一致まで証明するものではありません。

文章形式のAgent回答では、参照IDがすべて取得文書内にあることと、参照文書中の原文に一致する8文字以上の引用が少なくとも一つあることを確認します。JSON形式のclaimsでは各claimの引用を検査します。文言パターン検査はあらゆる訪問確約表現を検出するものではなく、回答の意味の正しさは別に確認が必要です。候補文書がない場合は、未検査の生成文を表示せず根拠不足を返します。

RAGは指示と資料JSONを一つのpromptに組み立てます。Python版のsystem/userメッセージの分離とは異なります。資料中の指示に従わないよう指定していますが、プロンプトインジェクションを完全に防ぐ保証はありません。処理順、検索範囲、検査条件はPL/SQL側で固定しています。

出力はCLOBで返し、`print_clob`でDBMS Outputへ分割表示します。表示上の改行はJSON文字列の途中に入る場合があります。機械処理ではDBMS Outputを再解析せず、返却CLOBを直接使用してください。

## Python版と開発用の検証

Python版の[rag.py](../src/webinar_demo/rag.py)、[business_ai.py](../src/webinar_demo/business_ai.py)、NL2SQLの自動評価コードは引き続き利用できます。Python版は参考・開発用で、本編で二重に実演する必要はありません。

```powershell
uv run --locked python -m webinar_demo.evaluate_plsql
```

準備済みDBに接続して、RAGの正常・異常ケースとAgentの5ケースを評価し、`local/plsql-demo-results.json`に保存します。LLM呼び出しを伴います。新パッケージだけの登録を含める場合は`--setup`を付けます。モデルの再ロードやデータ再投入は行いません。

2026-10-20の実機確認では、RAGの6ケースを各2回、入力拒否4ケース、不正応答拒否3ケース、Agent5ケースの計24ケースが成功しました。すべての呼び出しで終了後のチケットコンテキスト消去も確認しました。既存Pythonテストは80件成功、DBの再投入を伴う5件はスキップです。新しいSQLのVS Code SQL Developerでの画面操作確認は別途必要です。
