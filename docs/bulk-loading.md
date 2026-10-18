# 大量データを分割して投入し、途中から再開する

[環境準備](environment-setup.md)と標準データの動作確認を終えた方向けの、大量ロードの手順です。まず「Pythonから分割投入する」までを実行すれば、基本の投入・再開を確認できます。Object Storage経路と障害検証は必要に応じて参照してください。

**ロードとベクトル生成を分け、それぞれ小さな単位で確定します。** 本編の16文書はそのまま使い、負荷試験用には架空の文書を繰り返した専用データを生成します。今回確認した規模は1,000件・約400 KBです。大量データ処理の手順を示す例であり、大規模環境の性能評価や検索精度評価には使えません。

## 方式を選ぶ

| 条件 | 選択肢 | 本教材での扱い |
|---|---|---|
| 本編の小規模データ | SQLまたはPython | [共通データ](demo-data.md)を使用 |
| ローカルで生成し、分割して送れるデータ | `executemany` | 250件ごとにMERGE・検査・COMMIT |
| ファイルを共有したい、DB側でロードしたい | Object Storage＋`COPY_DATA` | 分割CSV→ステージング表→全列照合→本表へMERGE |
| ベクトル化に時間がかかる | ロード完了後に別ジョブで実行 | 8件ずつ確定。最初の32件だけを検証 |

件数だけで方式を決めず、本文の長さ、転送量、DBの余力、再実行の単位を測って選びます。小さいファイルではCOPY_DATAの起動処理が時間の大半を占める場合があります。本教材の測定から大規模時の優劣を推定しないでください。

## 専用表と権限を用意する

[環境準備](environment-setup.md)を完了し、既存のarakawalabに接続します。Pythonは本ディレクトリのuv環境を使います。

```powershell
uv sync --locked
uv run --locked python -m webinar_demo.bulk --generate --rows 1000 --part-size 250 --setup
```

ORAJAM41USERに次の3表を作成します。[DDL](../sql/bulk/70_create_bulk_tables.sql)はSQLクライアントからも実行できます。

| 表 | 用途 |
|---|---|
| OJ41_BULK_STAGE | COPY_DATAの受け皿。検査前の行を置く |
| OJ41_BULK_DOCS | 検査済み本文、ベクトル、生成状態 |
| OJ41_BULK_PARTS | データセット・経路・ファイル単位の完了／失敗記録 |

COPY_DATAを使う場合、ADMINで[04_bulk_directory.sql](../sql/admin/04_bulk_directory.sql)を一度実行します。ログ・拒否行ファイルを扱うため、ORAJAM41USERへ`DATA_PUMP_DIR`のREAD・WRITEを付与します。既存ユーザーを作り直す必要はありません。

DBからの読み取りには`OCI$RESOURCE_PRINCIPAL`を使用します。ローカルからのアップロードには`.env`のAPIキー設定を使用し、既存の名前空間とモデル用バケットを既定の配置先とします。必要な場合のみ次を`.env`へ追加してください。

```dotenv
# 空欄ならOCI_MODEL_REGION / OCI_MODEL_BUCKETを使用
OCI_BULK_REGION=
OCI_BULK_BUCKET=
```

ローカルの署名キー利用者には対象バケットへのオブジェクト作成・参照、DBのリソースプリンシパルには読み取りが必要です。別バケットへ変更した場合は双方の権限を確認します。

## Pythonから分割投入する

```powershell
# 250件を確定して停止する
uv run --locked python -m webinar_demo.bulk --route python --stop-after 1
# 完了済みファイルを検査して飛ばし、残りを投入する
uv run --locked python -m webinar_demo.bulk --route python
# もう一度実行しても、同じデータは増えない
uv run --locked python -m webinar_demo.bulk --route python
```

生成先は`data/generated/bulk/`です。各CSVの件数・行番号範囲・SHA-256を`manifest.json`へ記録します。同じ生成条件なら同じファイルを得られるため、記事ではデータを添付せず、この生成コマンドを紹介します。

投入コードは1ファイル分だけをメモリーに読み込みます。1ファイルの上限は10,000件で、標準は250件です。分割数に比例するmanifest情報も保持するため、ファイル数が極端に増える使い方は別途設計が必要です。

ファイルのハッシュ、各行の本文ハッシュ、識別子、連続した行番号を確認してから投入します。MERGEと完了記録は同じトランザクションで確定します。途中エラーではそのファイル分をロールバックし、失敗記録を残します。前のファイルの確定分は保持されます。

完了記録があっても、本表との全列照合で不一致になれば停止します。入力を変更したい場合は生成条件・データセットを改めて定義し、同じ識別子のファイルを手で書き換えて再開しないでください。

## Object Storageからロードする

```powershell
uv run --locked python -m webinar_demo.bulk --route cloud --stop-after 1
uv run --locked python -m webinar_demo.bulk --route cloud
```

このコマンドはCSVをアップロードしてからDBに接続します。配置先は`orajam41-bulk/<dataset_id>/<ファイルハッシュ>/<ファイル名>`です。既存ONNXの配置先とは別で、同名オブジェクトは上書きしません。再実行時は既存オブジェクトのハッシュメタデータを確認します。生成物と環境別SQLはGit管理外です。

CSVはUTF-8・BOMなし・LF、カンマ区切り、二重引用符による囲みです。本文には改行、カンマ、引用符を含めています。**本文に改行があるため、`type`は`csv with embedded`を指定します。** `csv`だけでは改行位置で別レコードになり、この環境では拒否されました。[Oracleの形式指定](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/format-options.html)も参照してください。

```sql
format => '{"type":"csv with embedded","delimiter":",","quote":"\"",
            "skipheaders":1,"characterset":"AL32UTF8",
            "rejectlimit":0,"blankasnull":false}'
```

本データの6列はすべて必須で、空文字・NULL・日付列はありません。Oracleでは空文字がNULLになるため、実データで両者の区別が必要なら別の表現を定義します。日付列を追加する場合はファイルの表記と`dateformat`を合わせます。本文は2,400文字以内の設計です。より長い文書は事前に分割するか、CLOB等を使う別のロード設計を検証してください。

処理順は、対象ファイルのステージング行を削除・確定→COPY_DATA→元CSVとの全列照合→DB内のMERGE→完了記録・確定です。COPY_DATAと後続MERGEは一体のトランザクションではありません。ロード失敗時にはステージングに行が残る可能性があるため、再実行時に同じデータセット・ファイルの行を消してからやり直します。本表には検査済みの行だけを反映します。

### SQLクライアントでCOPY_DATAを確認する

```powershell
uv run --locked python -m webinar_demo.bulk --render-sql
```

この操作は必要なCSVをアップロードし、`local/71_copy_one_part.sql`と`local/72_embed_one_batch.sql`を生成します。Database ActionsまたはVS Code SQL Developerで、ORAJAM41USERとして`71`をスクリプト実行すると、最初のファイルだけをステージング表にロードします。件数・行番号の重複を確認し、DBMS_OUTPUTにoperation_idを出します。

`71`はCOPY_DATAの学習用で、本表には反映しません。本表へ進めるときは`bulk --route cloud`を実行してください。同コマンドが完了記録のないファイルを再ロードし、元CSVとの全列照合とMERGEを行います。SQL学習用ファイルとPythonの完了記録は別に扱います。

## ベクトル生成を8件ずつ確定する

```powershell
uv run --locked python -m webinar_demo.bulk --embed --limit 32 --batch-size 8 --stop-after 1
uv run --locked python -m webinar_demo.bulk --embed --limit 32 --batch-size 8
```

`limit`はデータセット内の行番号の上限です。先頭32件のみを対象とし、残る968件は未生成にして負荷を抑えます。本文の先頭へ`passage: `を付け、DB内のMULTILINGUAL_E5_LARGEで生成します。

上記の既定方式は、各行へ`VECTOR_EMBEDDING`を適用します。8件はトランザクションの単位であり、配列入力APIの呼び出し件数ではありません。

生成状態はPENDING・DONE・FAILEDで管理します。エラー時はその8件の更新を戻し、FAILEDとエラーコードを記録します。同じコマンドで未完了分を再処理できます。セッション切断などで失敗記録自体を書けなくても、未確定分は再実行の対象です。接続を直してから進捗表を確認してください。

SQLクライアントでは生成済みの`local/72_embed_one_batch.sql`を実行します。先頭32件のうち未完了の最大8件を処理するため、最大4回で完了します。いずれの経路も同じデータセットを複数セッションから同時に処理しないでください。本教材には並列ワーカーの排他制御を実装していません。

同一本文のMERGEでは既存ベクトルを保持し、本文ハッシュが変われば未生成へ戻す設計です。ただし、同じモデル名でモデル本体を交換した場合や前処理を変更した場合は自動検知できません。モデル／前処理の版を管理し、対象ベクトルを明示的に再生成する運用が必要です。索引作成は今回の範囲外です。

## エラー時はファイルと生成状態を分けて調べる

[73_check_progress.sql](../sql/bulk/73_check_progress.sql)で、ファイル単位の記録、生成状態、`USER_LOAD_OPERATIONS`を確認します。COPY_DATA失敗時はoperation_idが呼び出し元へ返らないことがあるため、同ビューの対象表と最新実行を照合し、LOGFILE_TABLE・BADFILE_TABLEに示された表を参照します。ログの保持期限にも注意してください。[ロードの監視](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/load-data-cloud-monitor.html)

| 症状 | 対応 |
|---|---|
| DATA_PUMP_DIRへのアクセスエラー | ADMINで04の権限付与を確認 |
| COPY_DATAのORA-20003 | ログ・拒否行を調べる。今回の試験では数値列への文字列で発生 |
| 元CSVとの不一致 | 本表へ進めず、CSVの版・文字コード・列順・形式を確認 |
| ベクトル生成がFAILED | エラーと負荷を確認して再実行。必要ならbatch-sizeを縮小 |

実機検証は次のコマンドです。1,000件の専用データを確認し、17件の障害試験用データを入れ直し、先頭32件の専用ベクトルを再生成します。既存の本編用表は変更しません。

```powershell
uv run --locked python -m webinar_demo.evaluate_bulk
```

結果は`local/stage5-evaluation.json`へ出力します。出力された件数とエラー時の再開結果を確認してください。


## 複数の入力をUTL_TO_EMBEDDINGSへ渡す

配列入力方式も選べます。`--embedding-method array`を指定すると、未完了行を最大`batch-size`件集め、**1バッチにつき1回だけ**`DBMS_VECTOR.UTL_TO_EMBEDDINGS`を呼び出します。`provider=database`、`model=MULTILINGUAL_E5_LARGE`を指定するため、この変換ではOCI GenAIへアクセスしません。

```powershell
uv run --locked python -m webinar_demo.bulk --embed --embedding-method array --limit 32 --batch-size 8 --stop-after 1
uv run --locked python -m webinar_demo.bulk --embed --embedding-method array --limit 32 --batch-size 8
```

既にDONEの行は両方式ともスキップします。方式を切り替えただけでは再生成しません。比較には後述の専用評価コマンドを使います。

入力は`chunk_id`・`chunk_offset`・`chunk_length`・`chunk_data`を持つJSONの配列です。本実装では行番号をchunk_idへ、`passage: `付き本文をchunk_dataへ設定します。PL/SQLの`VECTOR_ARRAY_T`へ格納し、次の関数へまとめて渡します。

```sql
l_outputs := DBMS_VECTOR.UTL_TO_EMBEDDINGS(
  l_inputs,
  JSON('{"provider":"database","model":"MULTILINGUAL_E5_LARGE"}')
);
```

返却されたembed_idとembed_dataで元の行を照合し、件数・IDの重複・次元数・数値の妥当性を検査してから保存します。配列の位置だけで元の行と対応付けません。Python経路では結果をJSONで受け取り、FLOAT32ベクトルに変換して更新します。失敗時は同じバッチを戻し、FAILEDとして再実行可能にします。

SQLクライアント用には[75_embed_array_batch.sql](../sql/bulk/75_embed_array_batch.sql)を追加しました。`bulk --render-sql`で生成される`local/75_embed_array_batch.sql`を実行すると、最大8件を1回の配列呼び出しで変換します。既存の72は行単位の関数適用を説明するために残しています。

[公式リファレンス](https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/utl_to_embedding-and-utl_to_embeddings-dbms_vector.html)では配列入出力と、1入力の文字数制約を説明していますが、databaseプロバイダーでの配列件数の最大値は明示されていません。外部プロバイダー用の`batch_size`パラメーターと、本教材が配列へ詰める入力件数は別です。今回のdatabase設定にはそのパラメーターを渡していません。

### 呼び出し件数と性能を再測定する

```powershell
# 保存済みベクトルは変更せず、APIの配列件数と既存方式を比較する
uv run --locked python -m webinar_demo.evaluate_array
# 専用17件データの先頭16件を使い、失敗・再開とSQL版を確認する
uv run --locked python -m webinar_demo.evaluate_array_resume
```

最初のコマンドは1,000件の大量ロード用データが投入済みであることを前提とします。1・8・32・64・128・256件を順に1回ずつ渡し、件数・ID・本文・次元数を確認します。その後、同じ先頭32件を各方式で3回ずつ変換します。並行ジョブを動かさず、ウォームアップ後に方式の順序を交互に変えます。計時にはDB処理、通信、結果取得とPython側変換を含め、DBへの保存は含めません。

結果は`local/array-evaluation.json`と`local/array-resume.json`へ保存します。入力の文字数とUTF-8のバイト数も記録します。現行CLIのbatch-size上限256は教材側の実行範囲を制限する値で、Oracle製品の上限を表しません。
