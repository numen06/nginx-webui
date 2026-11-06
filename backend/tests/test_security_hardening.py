import os
from datetime import datetime, timedelta

import bcrypt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import auth, database
from app.models import Base, OperationLog, User
from app.routers import audit, auth as auth_routes, config, files, logs
from app.utils import logrotate


def test_initial_admin_has_private_random_password(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    engine = create_engine(f"sqlite:///{db_path}")
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session)

    database.init_db()
    secret_file = tmp_path / "initial-admin-password"
    password = secret_file.read_text().strip()
    assert secret_file.stat().st_mode & 0o777 == 0o600
    with session() as db:
        user = db.query(User).one()
        assert auth.verify_password(password, user.password_hash)
        assert not auth.verify_password("admin", user.password_hash)
        user.password_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
        db.commit()

    database.init_db()
    with session() as db:
        assert auth.verify_password(password, db.query(User).one().password_hash)


def test_login_limit_and_permissions_preserve_draft_access(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    password = "Test-Password-1234"
    with session() as db:
        db.add(User(username="operator", password_hash=auth.hash_password(password)))
        db.commit()

    def test_db():
        with session() as db:
            yield db

    app = FastAPI()
    for router in (auth_routes.router, config.router, audit.router, files.router, logs.router):
        app.include_router(router)
    app.dependency_overrides[database.get_db] = test_db
    monkeypatch.setattr(auth, "SECRET_KEY", "test-signing-key")
    monkeypatch.setattr(auth, "LOGIN_FAILURE_LIMIT", 2)
    monkeypatch.setattr(config, "save_config_content", lambda content: None)
    client = TestClient(app)
    credentials = {"username": "operator", "password": password}
    token = client.post("/api/auth/login", json=credentials).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/config", headers=headers, json={"content": "events {}"}).status_code == 200
    assert client.post("/api/config/reload", headers=headers).status_code == 403
    assert client.get("/api/files", headers=headers, params={"root_only": True}).status_code == 403
    assert client.get("/api/audit/logs", headers=headers).status_code == 200
    assert client.post("/api/audit/logs/cleanup", headers=headers, json={"retain_days": 185}).status_code == 403
    assert client.delete("/api/logs/rotate/file/access.log.2026-01-01", headers=headers).status_code == 403

    assert client.post("/api/auth/login-basic", auth=("operator", "bad")).status_code == 401
    assert client.post("/api/auth/login", json={**credentials, "password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json=credentials, headers={"X-Forwarded-For": "203.0.113.8"}).status_code == 429

    with session() as db:
        assert db.query(OperationLog).filter_by(action="user_login_failed").count() == 2
        db.query(User).one().password_hash = auth.hash_password("Changed-Password-1234")
        db.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_log_path_and_retention_follow_live_config(tmp_path, monkeypatch):
    prefix = tmp_path / "active"
    conf = prefix / "conf"
    conf.mkdir(parents=True)
    configured_log = tmp_path / "live logs" / "access.log"
    configured_log.parent.mkdir()
    (conf / "nginx.conf").write_text(f'http {{\n    access_log "{configured_log}" combined;\n}}\n')
    monkeypatch.setattr(logrotate, "get_active_version", lambda: {"install_path": prefix})
    assert logrotate._resolve_access_log_path() == str(configured_log)
    assert logrotate._resolve_error_log_path() == str(prefix / "logs" / "error.log")

    now = datetime.now()
    old = now - timedelta(days=190)
    recent = configured_log.with_name(f"access.log.{now:%Y-%m-%d}")
    old_fragment = configured_log.with_name(f"access.log.{old:%Y-%m-%d}")
    for log in (recent, old_fragment):
        log.write_text("record")
    os.utime(old_fragment, (old.timestamp(), old.timestamp()))
    assert logrotate.cleanup_old_logs(configured_log.parent, configured_log.name, retention_days=7) == [str(old_fragment)]
    assert recent.exists()
