"""Explicit, read-only checks. No cloud or database resources are created."""

import argparse

from webinar_demo.settings import ConfigurationError, db_parameters, load_settings, oci_config, require


def check_oci(values: dict[str, str]) -> None:
    import oci

    config = oci_config(values)
    if values.get("OCI_ADB_REGION"):
        config["region"] = values["OCI_ADB_REGION"]
    oci.config.validate_config(config)
    client = oci.database.DatabaseClient(config, timeout=(10, 30))
    if values.get("OCI_ADB_OCID"):
        databases = [client.get_autonomous_database(values["OCI_ADB_OCID"]).data]
    else:
        require(values, "OCI_ADB_COMPARTMENT_OCID")
        databases = oci.pagination.list_call_get_all_results(
            client.list_autonomous_databases, values["OCI_ADB_COMPARTMENT_OCID"]
        ).data
    matches = [db for db in databases if db.db_name.lower() == "arakawalab"]
    if len(matches) != 1:
        raise ConfigurationError(f"arakawalab の一致件数={len(matches)}。OCI_ADB_OCIDを指定してください。")
    db = matches[0]
    print(f"OCI APIキー認証: OK / DB={db.db_name} / version={db.db_version} / state={db.lifecycle_state}")
    print(f"mTLS required={db.is_mtls_connection_required} / private endpoint={bool(db.private_endpoint)}")


def check_db(values: dict[str, str], admin: bool) -> None:
    import oracledb

    with oracledb.connect(**db_parameters(values, admin)) as conn:
        conn.call_timeout = 30000
        with conn.cursor() as cur:
            cur.execute("SELECT SYS_CONTEXT('USERENV','DB_NAME'), SYS_CONTEXT('USERENV','SESSION_USER') FROM dual")
            db_name, username = cur.fetchone()
            # ADB can prepend a generated prefix to DB_NAME.
            actual = db_name.lower()
            if actual != "arakawalab" and not actual.endswith("_arakawalab"):
                raise ConfigurationError("接続先DB名が想定と異なります。後続確認を停止しました。")
            expected = "ADMIN" if admin else "ORAJAM41USER"
            if username.upper() != expected:
                raise ConfigurationError("実行ユーザーが想定と異なります。")
            print(f"DB接続: OK / user={username} / version={conn.version}")
            if admin:
                cur.execute("SELECT COUNT(*) FROM dba_users WHERE username='ORAJAM41USER'")
                print(f"ORAJAM41USER存在件数: {cur.fetchone()[0]}")
            else:
                cur.execute("SELECT COUNT(*) FROM user_mining_models WHERE model_name='MULTILINGUAL_E5_LARGE'")
                print(f"自スキーマの埋め込みモデル件数: {cur.fetchone()[0]}")
                cur.execute("SELECT COUNT(*) FROM all_tab_privs WHERE grantee='ORAJAM41USER' AND table_name='OCI$RESOURCE_PRINCIPAL' AND table_schema='ADMIN'")
                print(f"リソースプリンシパル直接付与件数: {cur.fetchone()[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oci", action="store_true", help="OCI APIキーでADBを参照")
    parser.add_argument("--db", action="store_true", help="デモユーザーで読み取り確認")
    parser.add_argument("--admin", action="store_true", help="ADMINで読み取り確認")
    args = parser.parse_args()
    try:
        values = load_settings()
        if not any((args.oci, args.db, args.admin)):
            print(".env形式: OK（値は非表示。接続は未実施）")
            for label, keys in (
                ("OCI", ("OCI_USER_OCID", "OCI_TENANCY_OCID", "OCI_FINGERPRINT", "OCI_KEY_FILE", "OCI_REGION")),
                ("DB", ("DB_DSN", "DB_PASSWORD")),
                ("ADMIN", ("DB_DSN", "DB_ADMIN_PASSWORD")),
            ):
                missing = [key for key in keys if not values.get(key)]
                print(label + ": " + ("設定あり（未検証）" if not missing else "未設定=" + ", ".join(missing)))
        if args.oci:
            check_oci(values)
        if args.db:
            check_db(values, False)
        if args.admin:
            check_db(values, True)
        return 0
    except ConfigurationError as exc:
        print(str(exc))
    except Exception as exc:
        # Do not dump SDK exceptions: they may include URLs or request parameters.
        detail = exc.args[0] if exc.args else None
        code = getattr(exc, "code", None) or getattr(detail, "full_code", None)
        print(f"接続確認失敗: {type(exc).__name__}, code={code or 'unavailable'}（秘密情報を含む詳細は非表示）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
