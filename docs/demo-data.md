# 共通データの生成・投入手順

題材は架空の業務用ラックサーバー。AX-100／BX-200／CX-300は機種名、DEV001などは台ごとの保守登録番号。

架空の保守問い合わせデータを生成し、arakawalabのORAJAM41USERへ投入します。標準データはナレッジ16件、文書断片16件、機器12件、契約12件です。[環境準備](environment-setup.md)を終えた方は、以下の「生成する」「投入する」「確認する」の順に実行してください。

## 固定する条件と確認ケース

基準日は2026年10月15日、乱数シードは41、生成器の版は2.0です。今日の日付やLLMの出力には依存しません。基準日を変更しても、開始日当日・終了日当日などの関係を保ちます。乱数は架空のシリアル番号にのみ使い、正解となる業務条件は固定します。

| データ | 保存先 | 件数・役割 |
|---|---|---|
| 固定ナレッジ | `data/seed/knowledge.json` → OJ41_KNOWLEDGE | 16件。架空機種AX-100、BX-200、CX-300 |
| 文書断片 | OJ41_CHUNKS | 16件。短い文書なので1文書1断片。タイトル＋改行＋本文 |
| 機器 | OJ41_DEVICES | 12件。C001の8件とC002の4件 |
| 契約 | OJ41_CONTRACTS | 12件。1機器1契約とする簡略化したモデル |
| 基準日・生成条件 | OJ41_RUN | 1件。STANDARD |
| 顧客 | OJ41_CUSTOMERS | 架空の顧客2件 |
| 受付チケット | OJ41_SUPPORT_CASES | SR001→C001、SR002→C002の2件 |
| 評価用質問 | `evaluation.json` | 14件。期待文書、契約条件、ツールの役割などを記録 |

契約は`ACTIVE`かつ「開始日 ≦ 基準日 ≦ 終了日」のとき有効とします。現地保守の対象は、さらにサービス範囲が`ONSITE`の契約です。これはデモ用の業務定義です。

| 機器 | 確認する条件 | 現地保守の対象 |
|---|---|---|
| DEV001 | 有効な契約 | 対象 |
| DEV002 | 昨日で期限切れ | 対象外 |
| DEV003 | 解約済み | 対象外 |
| DEV004 | リモートのみ | 対象外 |
| DEV005 | 開始日当日 | 対象 |
| DEV006 | 終了日当日 | 対象 |
| DEV007 | 明日から開始 | 対象外 |
| DEV008 | 有効な契約 | 対象 |
| DEV009〜012 | 別顧客C002 | C001の閲覧対象外 |

ナレッジには、同じE101でも機種によって意味が異なる例、旧版KB004、別顧客専用KB013、未公開KB014、社内限定KB015を含めています。KB016にはアポストロフィ、改行、カンマ、二重引用符があり、ロード時の文字の欠落を確認できます。これらの本文は実在製品の保守手順ではありません。

## 生成する

プロジェクトのルートで実行します。

```powershell
uv sync --locked
uv run --locked python -m webinar_demo.generate_data
```

出力先は`data/generated/standard/`です。6つのCSV、`40_load_data.sql`、`evaluation.json`、`manifest.json`を生成します。CSVはUTF-8（BOMなし）、区切りはカンマ、改行はLFです。空欄はNULLを表し、この標準データでは空文字とNULLを区別しません。日付はYYYY-MM-DDです。

`manifest.json`は生成条件、件数、各出力のSHA-256ハッシュを記録します。同じ版・シード・基準日なら、出力はバイト単位で一致します。派生ファイルはGit管理外とし、固定ナレッジと生成コードを配布します。

別の基準日を試す場合は、例えば次のように指定します。

```powershell
uv run --locked python -m webinar_demo.generate_data --as-of 2028-02-29 --seed 41 --output data/generated/leap-day
```

## 投入する

### SQLクライアントから実行する

データベースアクションまたはVS Code SQL Developerで、arakawalabのORAJAM41USERに接続します。未コミットの別作業がない専用セッションで、次のファイルを順に実行してください。

1. `sql/setup/35_create_demo_tables.sql`：表と閲覧用ビューを準備。
2. `data/generated/standard/40_load_data.sql`：標準データを投入。
3. `sql/setup/45_check_demo_data.sql`：件数、閲覧範囲、契約の期待結果を確認。

最初の2ファイルは、それぞれ全体で一つのPL/SQLブロックです。スクリプト実行機能では末尾の`/`を含めます。単一文として実行する場合はブロック全体を選択し、末尾の`/`を除きます。3つ目は読み取り専用のSELECT文なので、順に実行して結果を確認できます。チケットの開始から終了までは、同じDBセッションで実行してください。

表の準備は、存在する表を保持し、専用の閲覧用ビューを更新します。DDLには暗黙のコミットがあるため、途中で失敗した場合に一括で元へ戻る処理ではありません。既存表の列定義を自動変更する機能もありません。

投入は主キーによるMERGEで、同じデータを繰り返しても行数を増やしません。件数確認まで成功した後にコミットします。途中で失敗した場合は、そのセッションの未コミット変更をロールバックします。標準データ以外の行が混在すると件数検証で停止し、余分な行を自動削除しません。

### Pythonから実行する

`.env`のDB接続情報を使います。APIキーやGenAIへの接続は、この投入処理には不要です。

```powershell
uv run --locked python -m webinar_demo.load_data --setup
```

`--setup`は同じ表準備SQLの単一ブロックを実行します。データはCSVを読み、バインド変数付きMERGEを`executemany`で実行します。全列の照合と閲覧用ビューの検証後にコミットします。途中エラーでは全体をロールバックします。

生成SQLそのものをPythonから実行する検証経路も用意しています。独自のSQL分割処理は使わず、生成した単一のPL/SQLブロックを実行します。

```powershell
uv run --locked python -m webinar_demo.load_data --route sql
```

再生成後に`--input data/generated/leap-day`を指定すると、その生成条件の標準データに更新します。生成ファイルを手編集せず、固定ナレッジまたは生成器を修正して再生成してください。Python経路はハッシュと再生成結果を照合し、不一致ならDB操作前に停止します。

## 確認する

```powershell
uv run --locked python -m webinar_demo.load_data --verify-only --report local/stage2-validation.json
uv run --locked pytest -q --basetemp=local/pytest-stage2
```

DB確認では7表の全データ列を生成結果と比較します。閲覧可能な文書は12件、機器は8件、現地保守対象はDEV001・005・006・008です。文書断片のベクトル列は検索の準備で生成するため、投入直後はNULLのままです。

文書断片には本文ハッシュと前処理の版を保持します。再投入時、どちらかが変わればベクトルとモデル識別情報をNULLに戻し、古いベクトルが残らないようにします。同じ本文・前処理なら既存ベクトルを保持します。モデル自体を変更する場合の再計算は[検索の準備](search-rag.md)で扱います。入力の`passage: `接頭辞もベクトル生成時に付けます。

通常のpytestはDBに接続しません。実DBの投入経路テストを明示的に実行する場合は、以下を使います。

```powershell
$env:ORAJAM41_DB_TEST = '1'
uv run --locked pytest -q --basetemp=local/pytest-stage2-db
Remove-Item Env:ORAJAM41_DB_TEST
```

このテストは、まず既存内容が標準データと一致することを確認します。その後、標準データの7表の行をトランザクション内で削除・再投入し、SQLとPythonの新規投入経路をそれぞれ確認します。既存ベクトルがある場合は削除前に停止します。生成済みベクトルを維持したい場合は、このテストを実行せず`--verify-only`を使ってください。登録済みのモデルやAI設定は変更しません。

## 選択中の受付チケットから顧客を決める

後続の検索・RAG・エージェントでは、次のビューを共通で使います。

- `OJ41_VISIBLE_KNOWLEDGE`／`OJ41_VISIBLE_CHUNKS`：公開済みで、一般公開または当該顧客専用の文書。
- `OJ41_VISIBLE_DEVICES`：当該顧客の機器。
- `OJ41_VISIBLE_CONTRACTS`：当該顧客の契約と、固定基準日による有効・現地保守対象の判定。

メーカーの担当者が受付番号を選び、`OJ41_CASE_CTX.open_case('SR001')`でチケットを開きます。受付表からC001を取得して接続内に保持し、各ビューがその顧客の行だけを返します。担当者はSR002へ切り替えればC002に対応できます。顧客ごとのDBユーザーは作りません。チケット未選択・開始失敗後は公開文書を含めて0件です。

チケットの終了時は`OJ41_CASE_CTX.clear_case`を実行します。Pythonでは`case_scope(conn, case_id)`が正常時・例外時とも消去します。接続プールではこの処理をリクエスト境界で使い、ネストさせません。SQLクライアントでは開始から終了まで同じ接続を使います。

ORAJAM41USERは表の所有者なので、ベース表へ直接アクセスできます。このビュー構成はチケットへの他顧客情報の混入を防ぐための簡易的な制約で、所有者自身の権限を制限しません。NL2SQLの比較では4つの閲覧用ビューと制限不要の表を同じobject_listに指定し、enforce_object_list=trueのもとでANNOTATIONの有無を変えます。Python版は生成後のSQLを検査し、閲覧用ビュー以外を参照するSQLを実行前に拒否します。Agent用のOJ41_BUSINESS_AIは契約ビューだけをobject_listに指定し、enforce_object_list=trueを設定します。本番の担当者・アプリの権限管理は、認証・チケット認可・DB権限分離やDeep Data Securityなどで別途設計します。[NL2SQL・Agentの手順](nl2sql-agent.md)を参照してください。

## 大量データと障害時の扱い

標準データは小さいため、一括のトランザクションで投入します。大量データを扱う場合は、専用の生成器と表を使う[大量ロードの手順](bulk-loading.md)へ進んでください。分割した`executemany`とObject Storage経由の`DBMS_CLOUD.COPY_DATA`を試せます。

エラーが出た場合は、接続先、実行ユーザー、ファイルの生成条件、既存表の定義を確認してください。件数不一致の場合は、標準以外の行が混ざっていないかを調べます。未解決の問題はエラーコードと実行コマンドを問い合わせ時に添え、パスワードや`.env`の値は共有しないでください。

参照：[Oracle MERGE](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/MERGE.html)、[python-oracledbのバッチ実行](https://python-oracledb.readthedocs.io/en/stable/user_guide/batch_statement.html)。実際のドライバー版はuv.lockで固定しています。

用語：文書断片＝検索の単位。MERGE＝主キーに対応する行を更新し、なければ追加するSQL。SHA-256＝ファイルや本文の内容を照合するハッシュ値。
