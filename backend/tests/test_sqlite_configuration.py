import sqlite3

from app.database import _configure_sqlite_connection


def test_sqlite_connection_uses_wal_and_waits_for_busy_database(tmp_path):
    connection = sqlite3.connect(tmp_path / "app.db")
    try:
        _configure_sqlite_connection(connection, None)
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    finally:
        connection.close()
