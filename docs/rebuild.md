# モデルを含めて教材を再構築する

初めて記事を試す読者は、削除処理を実行せず、[環境準備](environment-setup.md)のユーザー作成・権限付与から始める。本書は既存の教材資産を消して、初回導入に近い条件で再現性を確認するための手順である。対象DBはarakawalab、ユーザーはORAJAM41USERに固定している。

## 1. 再取得できることを確認して退避する

```powershell
uv sync --locked
$env:PYTHONUTF8 = '1'
# 退避とモデル元ファイルの確認のみ。削除しない。
uv run --locked python -m webinar_demo.reset_demo
```

`local/rebuild-backup-<UTC日時>/`に教材の表（標準7表と大量ロード3表）、ベクトル、PL/SQLソース、AI定義、ツール履歴、オブジェクト一覧を保存する。モデルの重みはこの退避ファイルに含めない。DBのリソースプリンシパルで、.envのURIと同じ配置先にONNX本体と外部データの計5ファイルが存在することを確認する。ファイルが欠けている場合は削除へ進まない。

退避JSONは調査・照合用であり、ワンクリックで元のDBへ戻すインポーターではない。復旧はGitのコード、固定データ生成器、Object Storageのモデル元ファイルから行う。履歴の内容は退避JSONから参照する。local/には環境固有情報が含まれるため、公開しない。

## 2. 対象資産とモデルを削除する

**実演環境を一時的に使えなくする操作。既存データが必要なら、この手順を実行しない。** 

```powershell
uv run --locked python -m webinar_demo.reset_demo --apply --include-model
```

このコマンドも削除直前に新たな退避を作る。退避とモデル元ファイルの確認に失敗すると停止する。チーム→タスク→エージェント→ツール→AIプロファイル→ビュー・関数・パッケージ→表→モデルの順に、名前を固定した対象だけを削除する。表の削除はPURGEを伴い、DBのごみ箱からは復元できない。意図しない外部キーがある場合はCASCADEせず停止する。

ユーザー、パスワード、RP利用権限、Webアクセス、IAMポリシーは保持する。DBTOOLS$、COPY$、SYS_*、DM$*等を名前の前方一致で直接削除しない。モデルの内部オブジェクトはDROP_ONNX_MODELに管理を任せる。このため「ユーザーを削除して再作成した完全な空スキーマ」とは区別し、**モデル・教材表・AI定義がない状態からの再構築**と記録する。

SQLクライアントで行う場合は[90_reset_demo.sql](../sql/cleanup/90_reset_demo.sql)をローカルコピーし、退避後に`l_confirm`を`RESET_ORAJAM41_DEMO`、`l_drop_model`を`TRUE`へ変更する。このSQL自体には退避機能はない。初期値のままでは削除せず停止する。DDLは途中まで確定するので、失敗時はエラーと残った対象を確認してから再開する。

## 3. 記事の順序で作り直す

各コマンドの成功を確認して次へ進む。途中で失敗したら、その時点で停止し、接続先・モデル元ファイル・権限を確認する。削除コマンドを繰り返して最初からやり直す必要はない。

ロード直後にINMEMORY_ONNX_MODELで外部データのメモリー共有を有効にする処理を準備SQLへ含めている。再インポートでは共有設定がNOへ戻るため、EXTERNAL_DATA=YES、INMEMORY=YESを確認する。デモ・大量ロードの検証は並行起動せず、この順番で実行する。

```powershell
uv run --locked python -m webinar_demo.preflight --oci --db
uv run --locked python -m webinar_demo.setup_embedding --load
uv run --locked python -m webinar_demo.check_genai --python
uv run --locked python -m webinar_demo.check_genai --setup --db --nl2sql --agent
uv run --locked python -m webinar_demo.generate_data
uv run --locked python -m webinar_demo.load_data --setup
uv run --locked python -m webinar_demo.load_data --verify-only
uv run --locked python -m webinar_demo.search --prepare
uv run --locked python -m webinar_demo.business_ai --setup
uv run --locked python -m webinar_demo.evaluate_cases
uv run --locked python -m webinar_demo.nl2sql_compare --case-id SR001
uv run --locked python -m webinar_demo.evaluate_stage3 --rag
uv run --locked python -m webinar_demo.evaluate_stage4 --agents
uv run --locked python -m webinar_demo.check_sql_demos --agent
```

標準データ投入後、ベクトル生成前なら、`ORAJAM41_DB_TEST=1`を設定してDB結合テストも実行できる。これは標準データの削除・再投入・ロールバックを検証する試験なので、別のデータを入れた環境で実行しない。ベクトル生成済みの場合は保護のため停止する。

本編が復旧したら、発展編を検証する場合のみ次を実行する。Object Storageは専用の生成済みファイルを再利用し、共有ファイルを一括削除しない。

```powershell
uv run --locked python -m webinar_demo.evaluate_bulk
uv run --locked python -m webinar_demo.evaluate_array_resume
```

## 4. 結果を確認する

モデルは1024次元、機器・契約は各12件、ナレッジ・断片は各16件。検索・RAGでは16ケース、自然言語照会は4ケース、Agentは5ケースが検証対象である。Agentは文言の完全一致ではなく、引用、契約判定、ツール履歴で確認する。

VS Code SQL Developerでは、同じDB接続で`sql/demos/00b_embedding_basics.sql`、`01_vector_search.sql`、`02_nl2sql.sql`、`03_support_agent.sql`を順に実行する。SQL内の期待値と、記事の実行例を照合する。AgentはDBMS Outputを有効にして回答とツール履歴を確認する。

参照：[DROP_ONNX_MODEL](https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/drop_onnx_model-procedure-dbms_vector.html)、[DBMS_CLOUD_AI_AGENT](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/dbms-cloud-ai-agent-package.html)。


この教材は新規構築を対象とし、別バージョンのスキーマからの移行は扱わない。現在の教材を作り直す場合は、退避後にreset_demo --applyで教材資産を再構築する。モデルを保持する場合は--include-modelを付けず、00_capture_environment.sqlで登録・共有設定・1024次元を確認する。
