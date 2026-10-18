"""Regression checks for the destructive reset boundary."""
import sys
from unittest.mock import MagicMock

import pytest

from webinar_demo import reset_demo as reset


def test_sql_has_explicit_guard_and_fixed_scope():
    sql = reset.sql_template()
    assert "l_confirm VARCHAR2(80) := 'NOT_CONFIRMED'" in sql
    assert 'l_drop_model BOOLEAN := FALSE' in sql
    assert "SYS_CONTEXT('USERENV','CURRENT_SCHEMA') <> 'ORAJAM41USER'" in sql
    assert "db_name='arakawalab'" in sql
    for unsafe in ('DROP USER', 'CASCADE CONSTRAINTS', 'DROP TABLE SYS_', 'DROP TABLE DM$', 'DROP TABLE DBTOOLS$', 'DROP TABLE COPY$'):
        assert unsafe not in sql
    assert (reset.ROOT/'sql/cleanup/90_reset_demo.sql').read_text(encoding='utf-8') == sql


def test_failed_archive_prevents_deletion(monkeypatch):
    conn = MagicMock()
    manager = MagicMock()
    manager.__enter__.return_value = conn
    monkeypatch.setattr(sys, 'argv', ['reset_demo', '--apply', '--include-model'])
    monkeypatch.setattr(reset, 'load_settings', lambda: {})
    monkeypatch.setattr(reset, 'db_parameters', lambda _: {})
    monkeypatch.setattr(reset.oracledb, 'connect', lambda **_: manager)
    monkeypatch.setattr(reset, 'guard', lambda _: None)
    def fail(*args): raise ValueError('model source missing')
    monkeypatch.setattr(reset, 'snapshot', fail)
    with pytest.raises(ValueError, match='model source missing'):
        reset.main()
    conn.cursor.assert_not_called()
