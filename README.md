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
| 4 | [NL2SQLとAgent](docs/nl2sql-agent.md) | コメントの有無の比較、契約照会、ツール実行 |
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
