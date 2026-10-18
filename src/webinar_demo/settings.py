"""Read this project's .env only; never print configuration values."""

from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


class ConfigurationError(ValueError):
    pass


def load_settings(path: Path | None = None) -> dict[str, str]:
    env_path = path or ROOT / ".env"
    if not env_path.is_file():
        raise ConfigurationError(".env がありません。.env.example から作成してください。")
    # Disable ${...} interpolation so password characters remain literal.
    return {k: v or "" for k, v in dotenv_values(env_path, interpolate=False).items()}


def require(values: dict[str, str], *keys: str) -> None:
    missing = [key for key in keys if not values.get(key, "").strip()]
    if missing:
        raise ConfigurationError("未設定の項目: " + ", ".join(missing))


def local_path(value: str) -> str:
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else ROOT / path)


def oci_config(values: dict[str, str]) -> dict[str, str]:
    mapping = {
        "OCI_USER_OCID": "user", "OCI_TENANCY_OCID": "tenancy",
        "OCI_FINGERPRINT": "fingerprint", "OCI_KEY_FILE": "key_file",
        "OCI_REGION": "region",
    }
    require(values, *mapping)
    config = {dest: values[src] for src, dest in mapping.items()}
    config["key_file"] = local_path(config["key_file"])
    if not Path(config["key_file"]).is_file():
        raise ConfigurationError("OCI_KEY_FILE のファイルが見つかりません。")
    if values.get("OCI_KEY_PASSPHRASE"):
        config["pass_phrase"] = values["OCI_KEY_PASSPHRASE"]
    return config


def db_parameters(values: dict[str, str], admin: bool = False) -> dict:
    user_key = "DB_ADMIN_USER" if admin else "DB_USER"
    pass_key = "DB_ADMIN_PASSWORD" if admin else "DB_PASSWORD"
    require(values, "DB_NAME", user_key, pass_key, "DB_DSN")
    expected = "ADMIN" if admin else "ORAJAM41USER"
    if values["DB_NAME"].lower() != "arakawalab" or values[user_key].upper() != expected:
        raise ConfigurationError("接続対象は arakawalab / ADMIN または ORAJAM41USER に限定します。")
    result = {"user": values[user_key], "password": values[pass_key], "dsn": values["DB_DSN"]}
    for source, dest in (("DB_CONFIG_DIR", "config_dir"), ("DB_WALLET_DIR", "wallet_location")):
        if values.get(source):
            result[dest] = local_path(values[source])
    if values.get("DB_WALLET_PASSWORD"):
        result["wallet_password"] = values["DB_WALLET_PASSWORD"]
    result["tcp_connect_timeout"] = 15
    return result
