"""Render the model setup SQL; optionally load and verify the model."""

import argparse
from urllib.parse import urlparse

import oracledb

from webinar_demo.settings import ROOT, ConfigurationError, db_parameters, load_settings, require


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load", action="store_true", help="Register the model if absent, then verify")
    parser.add_argument("--verify", action="store_true", help="Verify the existing model without loading")
    args = parser.parse_args()
    try:
        values = load_settings()
        require(values, "OCI_MODEL_ONNX_URI")
        uri = values["OCI_MODEL_ONNX_URI"]
        parsed = urlparse(uri)
        if parsed.scheme != "https" or parsed.hostname != "objectstorage.ap-tokyo-1.oraclecloud.com":
            raise ConfigurationError("東京リージョンObject StorageのHTTPS URIを指定してください。")
        if parsed.query or parsed.fragment or not parsed.path.endswith("/multilingual_e5_large.onnx"):
            raise ConfigurationError("ONNX本体の通常URIを指定してください。")
        template = (ROOT / "sql/setup/10_load_embedding_model.sql").read_text(encoding="utf-8")
        sql = template.replace(
            "l_uri VARCHAR2(4000) := 'REPLACE_WITH_ONNX_URI';",
            "l_uri VARCHAR2(4000) := '" + uri.replace("'", "''") + "';",
        )
        output = ROOT / "local/10_load_embedding_model.sql"
        output.parent.mkdir(exist_ok=True)
        output.write_text(sql, encoding="utf-8")
        print("local/10_load_embedding_model.sql を生成しました。", flush=True)
        if not (args.load or args.verify):
            return 0
        with oracledb.connect(**db_parameters(values)) as conn:
            conn.call_timeout = 1200000
            with conn.cursor() as cur:
                cur.execute("SELECT SYS_CONTEXT('USERENV','DB_NAME'), SYS_CONTEXT('USERENV','SESSION_USER') FROM dual")
                db, user = cur.fetchone()
                if user != "ORAJAM41USER" or not (db.lower() == "arakawalab" or db.lower().endswith("_arakawalab")):
                    raise ConfigurationError("実際の接続先DB／ユーザーが想定と異なります。")
                if args.load:
                    print("モデルを確認・ロードしています。既存モデルは置換しません。", flush=True)
                    # This template deliberately has exactly one PL/SQL block.
                    cur.execute(sql.split("\n/\n", 1)[0])
                    print("モデル登録確認: 成功", flush=True)
                cur.execute("SELECT model_name, mining_function, algorithm, external_data, inmemory FROM user_mining_models WHERE model_name='MULTILINGUAL_E5_LARGE'")
                row = cur.fetchone()
                if not row:
                    raise ConfigurationError("自スキーマにモデルがありません。")
                print("モデル: " + " / ".join(str(value) for value in row), flush=True)
                if row[3:] != ('YES', 'YES'):
                    raise ConfigurationError("外部データとメモリー共有がYESではありません。--loadで教材モデルの設定を確認してください。")
                cur.execute("SELECT VECTOR_DIMENSION_COUNT(VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING :text AS data)) FROM dual", text="query: サーバーが応答しない")
                dimension = cur.fetchone()[0]
                if dimension != 1024:
                    raise ConfigurationError("モデルの出力次元が1024ではありません。")
                print("日本語入力のベクトル生成: 成功 / 次元=1024", flush=True)
        return 0
    except ConfigurationError as exc:
        print(str(exc))
    except oracledb.Error as exc:
        print("モデル準備失敗: " + exc.args[0].full_code + "（接続情報を含む詳細は非表示）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
