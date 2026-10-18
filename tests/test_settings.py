import pytest

from webinar_demo.settings import ConfigurationError, db_parameters, load_settings


def test_password_is_not_interpolated(tmp_path):
    path = tmp_path / ".env"
    path.write_text('DB_PASSWORD=abc${SECRET}xyz\n', encoding="utf-8")
    assert load_settings(path)["DB_PASSWORD"] == "abc${SECRET}xyz"


def test_wrong_schema_is_rejected():
    values = {"DB_NAME": "arakawalab", "DB_USER": "other_user", "DB_PASSWORD": "example", "DB_DSN": "example"}
    with pytest.raises(ConfigurationError):
        db_parameters(values)


def test_missing_settings_do_not_expose_password():
    with pytest.raises(ConfigurationError) as error:
        db_parameters({"DB_PASSWORD": "do-not-print-this"})
    assert "do-not-print-this" not in str(error.value)


def test_admin_uses_separate_password():
    values = {"DB_NAME": "arakawalab", "DB_USER": "orajam41user", "DB_ADMIN_USER": "ADMIN", "DB_PASSWORD": "demo", "DB_ADMIN_PASSWORD": "admin", "DB_DSN": "example"}
    assert db_parameters(values, admin=True)["password"] == "admin"
