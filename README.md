# Oracle AI Jam 41：インデータベースAIを試す

Autonomous AI Database 26aiで、DB内の埋め込みモデル、ベクトル検索、RAG、Select AI、Select AI Agentを試す教材です。架空のラックサーバーの保守問い合わせを題材に、文書と契約データを組み合わせます。

## 最初に読むもの

解説は[記事本文](article/qiita.md)を参照してください。初回公開後はQiita側を本文の原本とし、このファイルはQiitaから取得したミラーとして更新します。SQLやPythonの修正はコードと手順書に反映します。

既存のAutonomous AI Database 26ai、OCIの設定権限、Python 3.12、uv、VS Code SQL Developerを用意してください。教材の接続先チェックはDB名`arakawalab`とユーザー名`orajam41user`を前提としています。ほかの名前で使う場合は、接続先チェック・SQL・設定例を合わせて変更する必要があります。

| 順序 | 手順書 | 完了すること |
|---|---|---|
| 1 | [環境準備](docs/environment-setup.md) | ユーザー・権限・リソースプリンシパル・モデル・LLMの準備 |
| 2 | [データ生成・投入](docs/demo-data.md) | 固定ナレッジ16件、サーバー12台、契約12件などの投入 |
| 3 | [検索とRAG](docs/search-rag.md) | ベクトル生成、検索、根拠を渡した回答生成 |
| 4 | [NL2SQLとAgent](docs/nl2sql-agent.md) | ANNOTATIONの有無の比較、契約照会、ツール実行 |
| 任意 | [大量ロード](docs/bulk-loading.md) | 分割投入、配列による埋め込み、失敗後の再開 |
| 再構築時 | [退避・削除・再構築](docs/rebuild.md) | 既存の教材資産を作り直す。初回は不要 |

## ローカル環境を作る

```powershell
uv sync --locked
Copy-Item .env.example .env
```

新規環境で実行し、`.env`にご自身の接続情報を設定してください。設定値の説明は環境準備の手順にあります。モデル本体と外部データはご自身のObject Storageへ配置します。モデル資産、秘密鍵、Walletはこのリポジトリに含まれません。

PythonからOCIへはAPI署名キー、DBからOCIへはリソースプリンシパルを使います。SQLクライアントは`.env`を読み込まないため、環境固有SQLは準備コマンドで`local/`へ生成します。`local/`と`data/generated/`はローカル生成物であり、ダウンロードするファイルではありません。

## コードを確認する

```powershell
uv run --locked pytest -q
```

通常のテストはDB・OCIへ接続せず、DB結合テストはスキップします。DB結合テストはデータの削除・再投入を伴うため、データ投入手順の条件を確認してから明示的に有効にしてください。クラウドを使う検証は各手順書のコマンドで実行します。

SQLは`sql/admin/`、`sql/setup/`、`sql/demos/`に分かれています。チケットを開いてから検索・照会・終了するまでは同じDBセッションを使ってください。生成SQLやAgentの回答は、記事の例と異なる場合があります。結果・引用元・ツール履歴を照合してください。

問題を確認する際は、実行コマンド、エラーコード、使用した版を記録してください。問い合わせやIssueに`.env`、パスワード、秘密鍵を添付しないでください。

## ライセンス

コード・サンプルデータはMIT、記事・手順書・画像はCC BY 4.0です。[適用範囲](LICENSING.md)を参照してください。

## デモ・準備・検証コード一覧

本編はSQL／PL/SQLで実行します。Python版と自動評価コードは参考・開発用として残しています。[PL/SQL版の手順と検査範囲](docs/plsql-demos.md)も参照してください。

### 実演と参考デモ

| ファイル | 用途 |
|---|---|
| [00_capture_environment.sql](sql/demos/00_capture_environment.sql) | 環境・モデル・データ件数の確認 |
| [00b_embedding_basics.sql](sql/demos/00b_embedding_basics.sql) | 埋め込みと近傍検索の基礎 |
| [01_vector_search.sql](sql/demos/01_vector_search.sql) | 顧客・機種を絞ったベクトル検索 |
| [01b_rag.sql](sql/demos/01b_rag.sql) | PL/SQLによるRAGの3ケース |
| [02_nl2sql.sql](sql/demos/02_nl2sql.sql) | ANNOTATION有無のNL2SQL比較 |
| [03_support_agent.sql](sql/demos/03_support_agent.sql) | 通常Agentの実演・履歴表示 |
| [04_checked_agent.sql](sql/demos/04_checked_agent.sql) | 自動検査付きAgentの参考実装 |

### モデル・表・PL/SQLパッケージの準備

| ファイル | 用途 |
|---|---|
| [00_check_environment.sql](sql/setup/00_check_environment.sql) | 環境確認 |
| [10_load_embedding_model.sql](sql/setup/10_load_embedding_model.sql) | ONNXモデルのインポート |
| [30_check_genai.sql](sql/setup/30_check_genai.sql) | GenAI接続確認 |
| [35_create_demo_tables.sql](sql/setup/35_create_demo_tables.sql) | 表・チケット管理・閲覧ビューの作成 |
| [45_check_demo_data.sql](sql/setup/45_check_demo_data.sql) | 投入件数・契約判定の確認 |
| [50_embed_documents.sql](sql/setup/50_embed_documents.sql) | 文書のDB内ベクトル化 |
| [60_agent_context.sql](sql/setup/60_agent_context.sql) | Agentコンテキスト仕様 |
| [61_agent_context_body.sql](sql/setup/61_agent_context_body.sql) | 契約・文書検索ツールの固定SQL |
| [62_contract_tool.sql](sql/setup/62_contract_tool.sql) | 契約照会のツール関数 |
| [63_knowledge_tool.sql](sql/setup/63_knowledge_tool.sql) | 文書検索のツール関数 |
| [64_business_ai_template.sql](sql/setup/64_business_ai_template.sql) | プロファイル・Tool・Task・Agent・Teamの定義 |
| [65_answer_guard.sql](sql/setup/65_answer_guard.sql) | 回答検査パッケージの仕様 |
| [66_answer_guard_body.sql](sql/setup/66_answer_guard_body.sql) | RAG・Agentの引用と履歴の検査 |
| [67_rag.sql](sql/setup/67_rag.sql) | RAGパッケージの仕様 |
| [68_rag_body.sql](sql/setup/68_rag_body.sql) | DB内RAGの検索・生成・検査 |
| [80_checked_agent.sql](sql/setup/80_checked_agent.sql) | 自動検査Agentの仕様 |
| [81_checked_agent_body.sql](sql/setup/81_checked_agent_body.sql) | Agent実行・検査・状態の消去 |

### 管理者による準備

| ファイル | 用途 |
|---|---|
| [01_create_user.sql](sql/admin/01_create_user.sql) | ユーザー作成・権限付与 |
| [02_enable_resource_principal.sql](sql/admin/02_enable_resource_principal.sql) | リソースプリンシパルの有効化 |
| [03_enable_database_actions.sql](sql/admin/03_enable_database_actions.sql) | Database Actionsの接続準備 |
| [04_bulk_directory.sql](sql/admin/04_bulk_directory.sql) | 大量ロードの作業ディレクトリ |

### 大量データ

| ファイル | 用途 |
|---|---|
| [70_create_bulk_tables.sql](sql/bulk/70_create_bulk_tables.sql) | 大量ロード用の表 |
| [71_copy_one_part.sql](sql/bulk/71_copy_one_part.sql) | Object Storageから1分割を投入 |
| [72_embed_one_batch.sql](sql/bulk/72_embed_one_batch.sql) | 文書バッチの埋め込み |
| [73_check_progress.sql](sql/bulk/73_check_progress.sql) | ロード・埋め込みの進捗確認 |
| [75_embed_array_batch.sql](sql/bulk/75_embed_array_batch.sql) | 配列による埋め込み |

### 退避後の削除

| ファイル | 用途 |
|---|---|
| [90_reset_demo.sql](sql/cleanup/90_reset_demo.sql) | 明示確認後のデモ資産削除（破壊的操作） |

### Pythonの準備・参考実装・評価

| ファイル | 用途 |
|---|---|
| [array_embeddings.py](src/webinar_demo/array_embeddings.py) | 配列によるバッチ埋め込み |
| [bulk.py](src/webinar_demo/bulk.py) | 大量データの生成・分割ロード |
| [business_ai.py](src/webinar_demo/business_ai.py) | AI定義の準備とPython版Agent |
| [case_context.py](src/webinar_demo/case_context.py) | Pythonのチケットコンテキスト管理 |
| [check_genai.py](src/webinar_demo/check_genai.py) | PythonとDBからのGenAI接続確認 |
| [check_sql_demos.py](src/webinar_demo/check_sql_demos.py) | SQLデモの自動実行確認 |
| [evaluate_array.py](src/webinar_demo/evaluate_array.py) | 配列埋め込みの評価 |
| [evaluate_array_resume.py](src/webinar_demo/evaluate_array_resume.py) | 配列埋め込みの再開評価 |
| [evaluate_bulk.py](src/webinar_demo/evaluate_bulk.py) | 大量ロードの評価 |
| [evaluate_cases.py](src/webinar_demo/evaluate_cases.py) | チケット分離の評価 |
| [evaluate_nl2sql_annotations.py](src/webinar_demo/evaluate_nl2sql_annotations.py) | ANNOTATION有無の反復評価 |
| [evaluate_plsql.py](src/webinar_demo/evaluate_plsql.py) | PL/SQL版RAG・Agentの実機評価 |
| [evaluate_stage3.py](src/webinar_demo/evaluate_stage3.py) | 検索・RAGの評価 |
| [evaluate_stage4.py](src/webinar_demo/evaluate_stage4.py) | NL2SQL・Agentの評価 |
| [generate_data.py](src/webinar_demo/generate_data.py) | 固定データと投入SQLの生成 |
| [load_data.py](src/webinar_demo/load_data.py) | 固定データの投入・照合 |
| [nl2sql.py](src/webinar_demo/nl2sql.py) | Python版NL2SQLの生成・検査 |
| [nl2sql_compare.py](src/webinar_demo/nl2sql_compare.py) | NL2SQL比較プロファイルの準備と評価 |
| [preflight.py](src/webinar_demo/preflight.py) | ローカル・OCI・DBの接続準備確認 |
| [rag.py](src/webinar_demo/rag.py) | Python版RAG |
| [reset_demo.py](src/webinar_demo/reset_demo.py) | デモ資産の退避・削除 |
| [search.py](src/webinar_demo/search.py) | Python版ベクトル検索 |
| [settings.py](src/webinar_demo/settings.py) | .envからの設定読み込み |
| [setup_embedding.py](src/webinar_demo/setup_embedding.py) | ONNXモデルの配置確認・インポート |

単体テストとDB結合テストは[tests/](tests/)にあります。`data/generated/standard/40_load_data.sql`はデータ生成時に作成する投入SQLで、Git管理外です。
