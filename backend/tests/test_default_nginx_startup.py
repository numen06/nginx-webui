from pathlib import Path

from app import main
from app.routers import nginx_manager


def test_builtin_source_is_registered_when_production_version_already_exists(
    tmp_path: Path,
    monkeypatch,
):
    versions_root = tmp_path / "versions"
    build_root = tmp_path / "build"
    default_tar = tmp_path / "default-nginx" / "nginx-1.31.2.tar.gz"
    last_executable = versions_root / "last" / "sbin" / "nginx"
    default_tar.parent.mkdir(parents=True)
    default_tar.write_bytes(b"builtin nginx source")
    last_executable.parent.mkdir(parents=True)
    last_executable.write_bytes(b"existing production nginx")

    monkeypatch.setattr(
        main,
        "_get_install_path",
        lambda version: versions_root / version,
    )
    monkeypatch.setattr(
        main,
        "_get_nginx_executable",
        lambda path: path / "sbin" / "nginx",
    )
    monkeypatch.setattr(main, "_get_default_nginx_tar_path", lambda: default_tar)
    monkeypatch.setattr(
        nginx_manager,
        "_get_source_tar_path",
        lambda version: build_root / f"nginx-{version}.tar.gz",
    )

    def ensure_nginx_dirs():
        versions_root.mkdir(parents=True, exist_ok=True)
        build_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(nginx_manager, "_ensure_nginx_dirs", ensure_nginx_dirs)

    compile_calls = []
    upgrade_calls = []
    monkeypatch.setattr(
        main,
        "_compile_nginx_from_source",
        lambda *args: compile_calls.append(args),
    )
    monkeypatch.setattr(
        nginx_manager,
        "_upgrade_to_production_version",
        lambda version: upgrade_calls.append(version),
    )

    main._ensure_last_nginx_from_default_tar()

    registered_tar = build_root / "nginx-1.31.2.tar.gz"
    assert registered_tar.read_bytes() == default_tar.read_bytes()
    assert last_executable.read_bytes() == b"existing production nginx"
    assert compile_calls == []
    assert upgrade_calls == []
