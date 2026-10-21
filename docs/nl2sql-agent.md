# 自然言語照会と保守対応エージェント

本編はSQLクライアントで実行します。[SQL／PL/SQL版の準備と実行手順](plsql-demos.md)を参照してください。以下のPython版の手順は参考実装・開発用として残しています。

共通データの契約をSelect AIで照会し、Select AI Agentから文書検索と契約照会を呼び出します。対象はarakawalabのORAJAM41USERです。[検索の準備](search-rag.md)までのデータとベクトルを準備してから、以下を実行してください。

## 本編用のプロファイルとツールを準備する

```powershell
uv sync --locked
uv run --locked python -m webinar_demo.business_ai --setup
```

DBからOCI GenAIへはリソースプリンシパルを使います。モデル、リージョン、コンパートメントは.envから本編用AIプロファイルへ設定します。ローカルPythonはDB操作と結果の検証を担当し、ここでのLLM呼び出しはDB内で行います。

| オブジェクト | 役割 |
|---|---|
| OJ41_NL2SQL_BASELINE / OJ41_NL2SQL_TUNED | 同じ質問・同じ参照対象でANNOTATIONの有無を比較する専用プロファイル |
| OJ41_BUSINESS_AI | 固定SQLのPL/SQLツールを使うAgent用のLLM接続・生成設定 |
| OJ41_AGENT_CTX | 対象機器・質問・実行ID・呼び出し回数をセッション内に保持するパッケージ |
| OJ41_CONTRACT_TOOL | 閲覧可能な契約を読み、有効性と現地保守対象を返す関数 |
| OJ41_KNOWLEDGE_TOOL | 対象機種に合う公開文書と顧客専用手順を検索する関数 |
| OJ41_LOOKUP_CONTRACT／OJ41_SEARCH_KNOWLEDGE | 上記関数を公開するSelect AI Agentのツール |
| OJ41_SUPPORT_AGENT／TASK／TEAM | 単一エージェント、タスク、チーム |

`--setup`は専用のパッケージ・関数・AI設定を更新します。環境確認用オブジェクトは保持します。SQLクライアントからの初回準備は、`sql/setup/60_agent_context.sql`、61、62、63の順に実行し、続けて生成された`local/64_business_ai.sql`を実行します。64には環境固有値が入るためGit管理外です。続けて`local/65_nl2sql_profiles.sql`で比較用プロファイルと注釈を作成します。64と65は初回作成用で、再設定にはPythonの`--setup`を使います。

ツール2個、AIプロファイル、Agent、Task、Teamの登録SQLは[64_business_ai_template.sql](../sql/setup/64_business_ai_template.sql)でも確認できます。これは初回作成用のテンプレートです。コンパートメントのプレースホルダーを置き換え、リージョン・モデルを確認して使います。Pythonの準備処理で登録済みの場合は再実行せず、定義の参照に使ってください。FUNCTIONの入口は[62_contract_tool.sql](../sql/setup/62_contract_tool.sql)と[63_knowledge_tool.sql](../sql/setup/63_knowledge_tool.sql)、固定SQLを含む処理本体は[61_agent_context_body.sql](../sql/setup/61_agent_context_body.sql)です。

`OJ41_BUSINESS_AI`にはLLMの接続先・認証・生成パラメータだけを設定します。Agentは登録済みのPL/SQL関数を呼び、その内部で固定SQLを実行するため、NL2SQL用の`object_list`と`enforce_object_list`は指定しません。閲覧範囲はツールの固定SQLが参照するビューとPL/SQLの検査で制御します。準備処理はこの専用プロファイルを再作成するため、デモの実行中には準備処理を実行しないでください。

## デモC：参照範囲を制限し、注釈の有無を比較する

比較用の両プロファイルは、4つのOJ41_VISIBLEビューとOJ41_RUN、存在すればOJ41_BULK_PARTSをobject_listに指定します。object_list_mode=all、enforce_object_list=true、comments=falseを共通にし、annotationsだけをfalseからtrueへ変えます。ベース表と制限対象の文書を複製した大量ロード表は除外します。未分類のOJ41表・ビューがある場合は準備を停止します。

ビュー全体と6列にdescription注釈を登録します。既存のCOMMENTが残っていても、この比較ではLLMへの入力に含めません。準備と繰り返し検証は次のコマンドで行えます。

```powershell
uv run --locked python -m webinar_demo.evaluate_nl2sql_annotations --setup --repeats 3
uv run --locked python -m webinar_demo.nl2sql_compare --case-id SR001
```

前者はlocal/nl2sql-annotations-evaluation.jsonへ、後者はlocal/nl2sql-comparison.jsonへ保存します。注釈なしの応答は表示だけとし、注釈ありの生成SQLを構文木で検査して正解と照合します。生成側の参照候補は6オブジェクトですが、Python検証器が実行を許すSQLは、今回の契約照会に必要なOJ41_VISIBLE_CONTRACTS単独の照会に限定します。検証結果と対象選定の理由は[nl2sql-annotations-validation.md](nl2sql-annotations-validation.md)を参照してください。

以下の各ケースも、質問にビュー名・列名・SQL生成ルールを追加せず、TUNEDプロファイルに質問文だけを渡します。

```powershell
uv run --locked python -m webinar_demo.nl2sql --case-id SR001 --case onsite
uv run --locked python -m webinar_demo.nl2sql --case-id SR001 --case counts
uv run --locked python -m webinar_demo.nl2sql --case-id SR001 --case other
uv run --locked python -m webinar_demo.nl2sql --case-id SR001 --case expired
```

| ケース | 正解 |
|---|---|
| onsite：現地保守対象の機器 | DEV001、DEV005、DEV006、DEV008 |
| counts：機種別の現地保守対象数 | AX-100は3件、BX-200は1件 |
| other：別顧客DEV009の契約 | 0件 |
| expired：現在有効ではない契約 | DEV002、DEV003、DEV007 |

注釈を調整した後の繰り返し検証では、4つの質問とSR002での現地保守照会が各3回とも正解に一致しました。LLMの応答には変動があるため、以下の正解は照合基準として使います。

「現在」はOJ41_RUNの基準日2026-10-15を指します。`IS_ACTIVE`は契約状態と開始日・終了日を含めた判定、`ONSITE_ELIGIBLE`はさらにサービス範囲を考慮した判定です。ライフサイクル上の`STATUS='ACTIVE'`だけで現時点の有効性を判断しません。例えばDEV002はSTATUSがACTIVEでも期限切れです。

Python版は`DBMS_CLOUD_AI.GENERATE`の`showsql`でSQLを生成し、SQLGlotで構文木を検査します。許可するのは単一の閲覧用ビューに対するSELECT、既知の列、等値条件、COUNT、GROUP BY、ORDER BYなどに限定しています。UPPER／LOWERによる大文字小文字の処理も許可します。ベース表、他スキーマ、JOIN、サブクエリ、任意の関数、更新SQLは拒否します。

検査後は構文木からSQLを再生成して実行し、正解SQLの結果と比較します。質問ごとに条件に使える列も制限します。別顧客の照会は0件になるため、不要な条件が混ざっていても結果だけでは誤りを見落とすことがあります。この検証では条件列と結果の両方を確認します。今回の小さなSQLの範囲に合わせた検証器であり、任意のSQLを安全に実行する汎用の仕組みではありません。

SQLクライアントでは`sql/demos/02_nl2sql.sql`を使います。生成SQLは表示のみで、自動実行しません。参照先と条件を読んでから正解SQLと比較してください。Agentを使った同じセッションでSelect AIへ戻る場合は、`BEGIN DBMS_CLOUD_AI_AGENT.CLEAR_TEAM; END;`を実行してチーム設定を解除します。

## デモD：2つのツールから対応案を作る

```powershell
uv run --locked python -m webinar_demo.business_ai --case-id SR001 --device DEV001 --question '管理画面が開かない。最初に何を確認し、誰へ連絡すればよいですか。現地保守を頼めますか。'
uv run --locked python -m webinar_demo.business_ai --case-id SR001 --device DEV002 --question '管理画面が開かない。現地保守を利用できる？'
```

アプリケーションが最初に受付チケットを開き、対象サーバーがその顧客のものか確認してから、対象機器と質問をDBのセッションへ保存します。番号が別顧客ならLLMを呼ばず停止します。この問い合わせでは契約判定と文書検索の取得結果が必要です。呼び出し順序や回数は固定せず、同じ対象・依頼の根拠がそろったことを確認します。ツールの機器IDが最初の指定と異なればDB側で拒否します。顧客・機種は閲覧用ビューから決定し、LLMから渡された値を認証情報として扱いません。

文書検索では、一般公開文書と当該顧客専用文書から、それぞれ最も近い1件を取得します。AX-100の管理画面停止ではKB001とC001専用手順KB012が対象です。エラーコードを含む質問では、そのコードを含む文書に限定します。デモAの上位3件検索から、エージェントの用途に合わせて取得方法を調整しています。

Agentは、技術手順、顧客固有の連絡手順、契約上の現地保守可否、必要な承認をまとめて回答します。契約の可否はツールが返した判定結果を使い、LLMに再計算させません。現地保守対象外なら、承認を得れば訪問できるかのような案内を避けます。

出力は、根拠付きの技術手順、DBからの契約結果、対応方針、承認要否、ツール履歴です。現地保守対象かどうかはLLMの文章から判定せず、契約ツールの`ONSITE_ELIGIBLE`を使います。対象なら「承認後に現地保守の手配を検討」、対象外なら「現地保守の対象として手配しない」と表示します。実際の訪問予約、通知送信、契約更新は行いません。

自動検査は、各取得結果と標準履歴の成功状態・入力・返却値を照合します。履歴の呼出IDは一つの根拠に一度だけ対応付け、別実行の結果や架空の再照会を混ぜないようにします。4回の上限は無限ループを防ぐ予算であり、正解の呼び出し回数ではありません。

検査結果の`validation_scope`は`evidence_only`、`review_required`は`true`です。引用と取得結果の対応を確認しても、回答の意味や網羅性を保証するものではありません。確約に見える表現は`review_warnings`へ記録します。今回のツールは照会だけなので`action_status`は`not_executed`であり、予約や契約更新が完了したという意味にはなりません。更新操作を追加する場合は、ツール側で認可・前提条件・承認・冪等性を確認し、結果を実際の業務データと照合します。

技術手順は通常の日本語で生成し、すべての参照IDが取得文書に含まれることと、少なくとも1つの原文引用を検査します。引用の改行と空白は正規化して照合します。この検査だけで全主張の意味や適用条件が正しいとは判断できないため、最終的な対応案は担当者が確認します。初期検証では、管理画面が使えない質問に管理画面からのログ出力操作が混ざったため、取得する文書を絞りました。

## 実行履歴と制限を確認する

各ツールの返却値には実行IDを含めています。Python版は、そのIDで`USER_AI_AGENT_TOOL_HISTORY`のOUTPUTまたはTOOL_OUTPUTを照合し、両ツールの実行が記録されていることを確認します。自作のセッション内トレースと標準の履歴の両方を出力するため、回答だけを見てツールが動いたと推測する必要はありません。

SQLクライアント用の`sql/demos/03_support_agent.sql`は、新しい接続でDBMS Outputを有効にして実行します。生成回答とセッションのトレースは同じブロックで表示し、その後のSELECTで標準のツール履歴を確認します。Python側の引用検査・表示整形はSQLクライアントでは自動適用されないため、結果と根拠を目視で照合してください。

通常は各ツール1回で根拠がそろいますが、同じ結果を返す再照会も許容します。異なる結果が混在した場合は止め、必要な根拠の不足や標準履歴との不一致を検出します。DBのガードは1要求あたり4回までとし、5回目のツール処理を拒否します。PythonのDB呼び出しタイムアウトは180秒、LLMの出力上限は1600トークンです。これらは利用料金の上限ではありません。エージェント内部のLLM呼び出し回数はツールの回数と異なります。

エージェントは同じセッションで`SET_TEAM`してから`RUN_TEAM`を実行します。今回の環境では独自のUUIDをconversation_idとして渡すと拒否されたため、会話はDB側の設定に任せ、ケースごとに新しいDB接続を使用します。UUIDはツール履歴の照合にのみ使います。チームの長期記憶の参照件数は1としています。この環境では0を指定すると拒否されました。

## 検証を再実行する

```powershell
# ローカル検証：許可外SQL、引用、契約判定の扱いなど。
uv run --locked pytest -q --basetemp=local/pytest-stage4

# 実DB：契約9ケース、ID差し替え、呼び出し制限、自然言語照会4ケース。
uv run --locked python -m webinar_demo.evaluate_stage4

# 上記に加えて、エージェントの5ケースを実行。
uv run --locked python -m webinar_demo.evaluate_stage4 --agents
```

結果は`local/stage4-evaluation.json`へ保存します。`complete`がtrueのときだけ、その実行で要求したケースが完了しています。エージェントのみ再評価する`--agents-only`では、既存の自然言語照会結果を保持します。実行範囲と結果の新旧を混同しないでください。

生成SQLが許可外なら実行せず停止します。エージェントの反復失敗や引用検証エラーも成功扱いにはしません。直近の実際の回答とトレースは`local/agent-last-run.json`で確認できます。

所有者スキーマ内のビューでは所有者自身の直接参照権限を制限できない点は、[共通データの手順](demo-data.md)と同じです。本番では実行権限とデータ所有権を分離して設計してください。

参照：[DBMS_CLOUD_AI_AGENT](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/dbms-cloud-ai-agent-package.html)。この環境では標準履歴のOUTPUTにツールの返却値が入り、TOOL_OUTPUTはNULLでした。



## チケットの切替と後始末

チケットIDがSR001なら顧客IDはC001、SR002ならC002です。同じDBユーザーで切替でき、担当者自身が選択します。CLIは`--case-id`で指定し、省略時はSR001です。SQLデモは冒頭のopen_caseと末尾のclear_caseまで同じ接続で実行します。途中で中断した場合もclear_caseを実行するか接続を閉じてください。Agentは会話IDを作成してRUN_TEAMに渡します。正常時・例外時とも実行状態と会話IDのセッション設定を消去し、Pythonの外側のcase_scopeがチケットを消去します。

`evaluate_cases`は未選択、別顧客番号、SR002への切替、開始失敗、例外、別接続、旧Agent呼び出しの拒否を検証します。Agentの5ケースはSR001のDEV001・DEV002・DEV004・未知コードと、SR002のDEV009です。SR001でDEV009を指定するケースはLLM呼び出し前の拒否を別途確認します。

```powershell
uv run --locked python -m webinar_demo.evaluate_cases
uv run --locked python -m webinar_demo.business_ai --case-id SR002 --device DEV009 --question '管理画面が開かない。現地保守を利用できる？'
```
