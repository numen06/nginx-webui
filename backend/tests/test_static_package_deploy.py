from pathlib import Path

import pytest

from app.utils.static_package import (
    normalize_static_access_path,
    rewrite_static_entry_paths,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "/"),
        ("/", "/"),
        ("portal", "/portal/"),
        ("/apps/portal", "/apps/portal/"),
    ],
)
def test_normalize_static_access_path(raw, expected):
    assert normalize_static_access_path(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["../portal", "/%2e%2e/portal", "/foo%2fbar/", "/portal?debug=1", r"\portal"],
)
def test_normalize_static_access_path_rejects_unsafe_values(raw):
    with pytest.raises(ValueError):
        normalize_static_access_path(raw)


def test_rewrite_static_entry_paths_for_subpath(tmp_path: Path):
    index = tmp_path / "index.html"
    index.write_text(
        '<link href="/assets/app.css">'
        '<script src="/assets/app.js"></script>'
        '<img src="//cdn.example.com/logo.png">'
        '<a href="/dashboard">dashboard</a>',
        encoding="utf-8",
    )

    changed = rewrite_static_entry_paths(tmp_path, "/portal/")

    assert changed == ["index.html"]
    content = index.read_text(encoding="utf-8")
    assert 'href="/portal/assets/app.css"' in content
    assert 'src="/portal/assets/app.js"' in content
    assert 'src="//cdn.example.com/logo.png"' in content
    assert 'href="/portal/dashboard"' in content

    # 重复部署或重试时不能重复添加访问路径。
    assert rewrite_static_entry_paths(tmp_path, "/portal/") == []
