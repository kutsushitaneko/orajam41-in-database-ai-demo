# 環境準備：arakawalabのorajam41userで実行する

Autonomous AI Database 26aiで、ユーザー作成からDB内の埋め込みモデル、OCI Generative AI、Select AI Agentの動作確認まで進めます。既存DBの管理権限とOCIのIAM設定権限を持つ方を対象とします。

## DBは既存環境を使い、デモ用スキーマを作る

既存のAutonomous AI Database 26ai `arakawalab`に、DBユーザー`orajam41user`を作成します。引用符なしで作成するため、データディクショナリ上の名前は`ORAJAM41USER`です。表、ビュー、PL/SQLツール、埋め込みモデル、AIプロファイル、エージェント定義はすべてこのスキーマに作ります。他のユーザーのデモ表やモデルには依存しません。

ADMINはユーザー作成・権限付与・リソースプリンシパルの利用許可に使います。データベース本体の新規作成は不要です。IAMの動的グループやポリシー、モデルを置くObject StorageはDBスキーマの外にある前提条件です。

## 認証は接続経路ごとに分ける

| 接続経路 | 認証 | 設定場所 |
|---|---|---|
| Python→ADB | DBユーザーとパスワード、必要に応じてWallet | .envのDB_* |
| Python→OCI API | OCI API署名キー認証（ユーザーOCID・テナンシOCID・指紋・秘密鍵） | .envのOCI_*。秘密鍵本体はファイルに置き、パスを記載 |
| ADB→OCI GenAI／Object Storage | ADBのリソースプリンシパル | IAMポリシーとDB側のOCI$RESOURCE_PRINCIPAL |

ローカルのAPI署名キーをDBへ登録する手順は使いません。OCI GenAIのBearer型APIキーとも区別します。OCI関係の環境固有値は`.env`に集約し、SQLに必要な値だけローカル作業コピーへ転記します。SQLクライアントは`.env`を自動読込しません。以下の準備コマンドは`.env`から環境別SQLを`local/`へ生成します。この生成物はGit管理外です。

## 1. ADMINでユーザーを作成する

データベースアクションまたはVS Code SQL Developerから、`arakawalab`のADMINへ接続します。[ユーザー作成SQL](../sql/admin/01_create_user.sql)を開き、実際のパスワードをローカル作業コピーで指定して実行します。公開用ファイルはプレースホルダーのまま保持します。SQLはプレースホルダーのままではユーザーを作成しません。

パスワードはADBの要件を満たすものを使います。SQL文字列にシングルクォートを含める場合は二重化が必要です。SQL実行画面の履歴にパスワードを残したくない場合は、ADMINのDatabase Users画面から同じ名前で作成し、以下の権限だけを付与する方法も使えます。

| 権限・設定 | 用途 |
|---|---|
| CREATE SESSION | デモユーザーとして接続 |
| CREATE TABLE / VIEW / SEQUENCE | デモデータと照会用ビューの作成 |
| CREATE PROCEDURE | PL/SQLツールの作成 |
| CREATE MINING MODEL | 自スキーマへのONNXモデル登録 |
| EXECUTE ON DBMS_CLOUD | Object Storage等へのアクセス |
| EXECUTE ON DBMS_VECTOR | モデル登録とベクトル処理 |
| EXECUTE ON DBMS_CLOUD_AI | Select AI |
| EXECUTE ON DBMS_CLOUD_AI_AGENT | Select AI Agent |
| DATA表領域のQUOTA 10G | 大きなモデルと小規模デモデータの初期枠。実測後に調整 |

この教材で使う基本権限です。大量ロード用の追加権限は末尾に記載します。DBAやANY系権限はデモユーザーへ付けません。ユーザーが既に存在する場合は作成SQLを停止し、既存の所有物と権限を確認します。DDLは途中まで確定するため、権限付与だけ失敗した場合もユーザーを削除してやり直さず、不足した権限を確認します。

ユーザー作成の考え方は[Oracle公式手順](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/manage-users-create.html)を参照してください。

## 2. ADBのリソースプリンシパルにOCIアクセスを許可する

IAM管理者が、対象の`arakawalab`のOCIDに限定した動的グループを確認・作成します。既存の設定がある場合は再利用します。動的グループの主体はDBユーザーではなくADBです。スキーマ別の利用可否はDB側で制御します。

動的グループの一致ルールとポリシーは、実際のアイデンティティドメインとコンパートメントに合わせて確定します。次は設計用テンプレートです。

```text
resource.id = '<ARAKAWALAB_ADB_OCID>'

Allow dynamic-group <DOMAIN>/<DYNAMIC_GROUP> to use generative-ai-chat in compartment id <GENAI_COMPARTMENT_OCID>
Allow dynamic-group <DOMAIN>/<DYNAMIC_GROUP> to read objects in compartment id <MODEL_COMPARTMENT_OCID> where target.bucket.name = '<MODEL_BUCKET>'
```

モデルファイルを取得するためのObject Storage権限は読み取りを基本にします。バケット一覧やオブジェクト一覧を確認する操作を加える場合は、そのAPIに必要な権限を別に確認します。GenAIはChat呼び出しを基本とし、実際に使うモデル・APIが別のリソース権限を必要とする場合に調整します。テンプレートの値は利用環境に合わせて置き換えてください。

IAM設定の後、ADMINで[リソースプリンシパル有効化SQL](../sql/admin/02_enable_resource_principal.sql)を実行します。ADMIN側の有効化を確認した上で、`ORAJAM41USER`への利用を許可します。他ユーザーへ許可を再付与する権限は渡しません。IAMの変更は反映に時間がかかる場合があります。

参照：[ADBのリソースプリンシパル](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/resource-principal.html)、[ENABLE_RESOURCE_PRINCIPAL](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/dbms-cloud-admin.html)、[OCI GenAIのIAM](https://docs.oracle.com/en-us/iaas/Content/generative-ai/iam-policies.htm)。

## 3. データベースアクションで使う場合はWebアクセスを設定する

ADMINのDatabase Users画面でWeb Accessを有効にするか、[設定SQL](../sql/admin/03_enable_database_actions.sql)を実行します。その後、`orajam41user`としてログインし直します。VS CodeからのSQL接続だけなら、この設定は必須ではありません。表へのAutoREST設定は行いません。

## 4. ローカルPythonの設定を用意する

このプロジェクトはPython 3.12とuvを使います。`.env.example`を`.env`へコピーし、OCI関係のパラメータとDB接続情報を設定します。Windowsのパスは`C:/...`形式にします。秘密鍵そのものを`.env`へ貼らず、`OCI_KEY_FILE`にパスを設定します。既存のOCI configを初期設定の参考にできますが、実行時は`.env`だけからOCI設定を構築します。

```powershell
uv sync --locked
uv run --locked python -m webinar_demo.preflight
uv run --locked python -m webinar_demo.preflight --oci
uv run --locked python -m webinar_demo.preflight --admin
uv run --locked python -m webinar_demo.preflight --db
```

`--oci`はAPI署名キーでADBの情報を参照します。対象OCIDを設定するか、対象コンパートメントを指定してください。今回のADB管理APIには`OCI_ADB_REGION=ap-tokyo-1`を使い、GenAIのリージョンは別に設定します。`--admin`と`--db`は読み取り確認のみです。これらのコマンドはユーザーやクラウド資源を作成しません。OCIに接続できてもDBに接続できるとは限らないため、それぞれを確認します。

TLS接続文字列またはWalletのTNS別名を`DB_DSN`へ設定します。Walletが必要な構成では`DB_CONFIG_DIR`、`DB_WALLET_DIR`、`DB_WALLET_PASSWORD`も設定します。実際の接続方式は対象DBの設定を調べて確定します。

uvのキャッシュへの書き込みに失敗する場合は、書き込み可能な`UV_CACHE_DIR`を指定して再試行してください。

## 5. モデル・LLM・エージェントの確認へ進む

ユーザー作成後、[環境確認SQL](../sql/setup/00_check_environment.sql)を`ORAJAM41USER`で実行します。モデルは他スキーマを参照せず、同スキーマへ`MULTILINGUAL_E5_LARGE`としてロードします。Object Storageへの認証には`OCI$RESOURCE_PRINCIPAL`を指定します。

Select AIのプロファイルも`credential_name`を`OCI$RESOURCE_PRINCIPAL`とし、対象オブジェクトは`ORAJAM41USER`内のデモ用表・ビューに限定します。[公式のSelect AI例](https://docs.oracle.com/en/database/oracle/oracle-database/26/selai/use-select-ai-ai-providers.html)を基に、モデルとリージョンを確認してから環境別SQLを作成します。

### 変換済みモデルをロードする

変換済みのONNX本体と外部データを、ご自身のObject Storageバケットへ配置してください。以下は教材で使用した変換済みモデルの構成例です。変換方法は[multilingual-e5-largeのインポート手順](https://qiita.com/yuji-arakawa/items/29e20088cebdd2bd7296)を参照してください。

| ファイル | サイズ（bytes） |
|---|---:|
| multilingual_e5_large.onnx | 5,569,359 |
| multilingual_e5_large_0.data | 993,251,328 |
| multilingual_e5_large_1.data | 218,103,808 |
| multilingual_e5_large_external_data.json | 67,234 |
| multilingual_e5_large_largeTensor_0.data | 1,024,008,192 |

`.env`の`OCI_MODEL_ONNX_URI`には、ONNX本体の通常のObject Storage URIを設定します。ロードはDB側の`DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD`で行うため、モデルをローカルPCへダウンロードする必要はありません。外部データファイルも同じ配置先から読み込まれます。

```powershell
# .envからSQLクライアントで実行するファイルを生成する（DB操作なし）
uv run --locked python -m webinar_demo.setup_embedding

# Pythonから同じPL/SQLを実行し、ロードと日本語入力の1024次元出力を確認する
uv run --locked python -m webinar_demo.setup_embedding --load

# 登録済みモデルの動作だけを確認する
uv run --locked python -m webinar_demo.setup_embedding --verify
```

データベースアクションまたはVS Code SQL Developerを使う場合は、生成された`local/10_load_embedding_model.sql`を開き、`ORAJAM41USER`で実行します。このファイルには実際のURIが入るためGit管理外です。公開用の原本は`sql/setup/10_load_embedding_model.sql`です。

既に同名のモデルがある場合は置換せず、そのモデルの出力を確認します。1024次元の出力確認だけで検索品質が保証されるわけではないため、後続のデモデータで検索結果を別途検証します。大きなモデルのロードを完了してから、データ投入へ進んでください。

今回のロードは成功し、日本語の質問から1024次元のベクトルを生成できました。

### 再ロード後は外部データのメモリー共有を有効にする

モデルは外部データを含めて約2.2 GBあります。再ロード後に埋め込み処理を並行実行したところ、PGA上限のORA-04036が発生しました。その時点のUSER_MINING_MODELSはEXTERNAL_DATA=YES、INMEMORY=NOでした。

準備SQLに次の処理を追加しました。`setup_embedding --load`は登録済みモデルにもこの設定を適用し、EXTERNAL_DATAとINMEMORYがともにYESであることを検査します。

```sql
BEGIN
  DBMS_VECTOR.INMEMORY_ONNX_MODEL(
    model_name => 'MULTILINGUAL_E5_LARGE', enable => TRUE);
END;
/
SELECT model_name, external_data, inmemory
FROM user_mining_models WHERE model_name='MULTILINGUAL_E5_LARGE';
```

再インポートするとINMEMORYはNOへ戻るため、ロード後に毎回設定します。外部イニシャライザを共有する機能で、近似ベクトル索引の設定とは別です。共有メモリーにも空きが必要であり、どの構成でもメモリー不足がなくなる保証ではありません。教材の検証は順番に実行し、メモリー不足時は同時実行数とDBの資源を確認します。[INMEMORY_ONNX_MODEL](https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/inmemory_onnx_model-dbms_vector.html)

## 6. 指定したGenAIとエージェントを確認する

モデルは`xai.grok-4.3`、リージョンは`us-chicago-1`です。ADBとモデルを置いたObject Storageは東京、LLMはChicagoで動きます。DBからLLMへ送る質問やメタデータ等はリージョンをまたぐ構成です。

`.env`に`OCI_GENAI_MODEL_ID`、`OCI_GENAI_REGION`、`OCI_GENAI_COMPARTMENT_OCID`を設定します。`OCI_GENAI_ENDPOINT`は通常空欄とし、SDKがリージョンから接続先を決定します。今回のコードはオンデマンドのモデルIDを使う構成です。

```powershell
# ローカルPython→GenAI：OCI API署名キー認証
uv run --locked python -m webinar_demo.check_genai --python

# DB内の確認用オブジェクトを作成し、GenAI・NL2SQL・エージェントを確認
uv run --locked python -m webinar_demo.check_genai --setup --db --nl2sql --agent
```

確認用オブジェクトはすべてORAJAM41USER内に作成します。本編の保守データとは独立した環境確認用です。`--setup`を再実行すると、この確認専用プロファイルとビュー・関数を現在の設定に合わせて更新します。ツール・タスク・エージェント・チームは未作成の場合に作成します。

| オブジェクト | 用途 |
|---|---|
| ORAJAM41_GENAI_SMOKE | リソースプリンシパルでGenAIを呼ぶAIプロファイル |
| ORAJAM41_ENV_PROBE | PROBE_VALUE=41を返す確認用ビュー |
| ORAJAM41_PROBE_STATUS | 状態を返し、呼び出し確認用のセッションマーカーを設定するPL/SQL関数 |
| ORAJAM41_SMOKE_TOOL／AGENT／TASK／TEAM | 単一ツールを1回呼ぶ最小エージェント構成 |

生成SQLは画面に表示し、自動実行しません。生成されたSELECTが確認用ビューと列を参照することを確認し、別に実行した正解SQLの結果41と比較します。

この接続確認用テストでは、同じセッションで`DBMS_CLOUD_AI_AGENT.SET_TEAM`を実行してから`RUN_TEAM`を呼びます。本編ではRUN_TEAMへteam_nameとCREATE_CONVERSATION()で取得したconversation_idを渡すため、SET_TEAMは不要です。単なる回答文だけで実行成功と判断せず、PL/SQL関数が設定したCLIENT_INFOとツールの実行履歴で呼び出しを確認します。

SQLクライアント向けの初回作成用SQLは`local/20_genai_smoke_setup.sql`に生成されます。既に作成した環境では重複作成せず、`sql/setup/30_check_genai.sql`で動作を確認してください。エージェントのSET_TEAMとRUN_TEAMは一つのPL/SQLブロックにまとめてあり、結果はクライアントのDBMS Outputで確認します。

期待する結果は、PythonのChat APIがHTTP 200、DB側のchatがOK応答、エージェントがSTATUS=READY／PROBE_VALUE=41を返すことです。続いて[共通データ](demo-data.md)を投入し、検索・RAG・エージェントを試してください。

参照：[Select AIのOCIプロバイダー設定](https://docs.oracle.com/en/database/oracle/oracle-database/26/selai/use-select-ai-ai-providers.html)、[DBMS_CLOUD_AI_AGENT](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/dbms-cloud-ai-agent-package.html)。

## Appendix：COPY_DATAを使う場合の追加権限

大量ロードを実行する場合は、ADMINで[04_bulk_directory.sql](../sql/admin/04_bulk_directory.sql)を実行します。COPY_DATAのログ・拒否行ファイルを扱うため、`GRANT READ, WRITE ON DIRECTORY DATA_PUMP_DIR TO orajam41user`を付与します。実機では未付与時にORA-06564が発生し、付与後に解消しました。[OracleのDBMS_CLOUDリファレンス](https://docs.oracle.com/en/database/oracle/oracle-database/26/arpls/dbms_cloud.html)

Object Storageからの読み取りは引き続きリソースプリンシパルを使用します。ローカルのアップロードはAPIキー認証です。配置先、専用表、再開手順は[大量ロード](bulk-loading.md)を参照してください。
