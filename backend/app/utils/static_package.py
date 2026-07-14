"""静态资源包的访问路径处理。"""

import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote


_ROOT_RELATIVE_HTML_URL = re.compile(
    r"(?P<prefix>\b(?:src|href|poster)\s*=\s*(?P<quote>[\"']))"
    r"(?P<url>/(?!/)[^\"']*)"
    r"(?P=quote)",
    re.IGNORECASE,
)


def normalize_static_access_path(access_path: Optional[str]) -> str:
    """把静态站点访问路径规范为以 / 开头、以 / 结尾的 URL 路径。"""
    value = (access_path or "/").strip()
    if not value:
        return "/"
    if "\\" in value or "?" in value or "#" in value:
        raise ValueError("访问路径不能包含反斜杠、查询参数或锚点")
    if any(ord(character) < 32 for character in value):
        raise ValueError("访问路径不能包含控制字符")
    if not value.startswith("/"):
        value = f"/{value}"

    segments = [segment for segment in value.split("/") if segment]
    decoded_segments = [unquote(segment) for segment in segments]
    if any(segment in {".", ".."} for segment in decoded_segments):
        raise ValueError("访问路径不能包含 . 或 ..")
    if any(
        "/" in segment
        or "\\" in segment
        or any(ord(character) < 32 for character in segment)
        for segment in decoded_segments
    ):
        raise ValueError("访问路径包含无效的转义字符")
    return "/" if not segments else f"/{'/'.join(segments)}/"


def rewrite_static_entry_paths(target_dir: Path, access_path: str) -> List[str]:
    """修正 HTML 中的根绝对地址，让构建产物可部署在 Nginx 子路径下。"""
    if access_path == "/":
        return []

    rewritten_files: List[str] = []
    for html_file in target_dir.rglob("*.html"):
        if not html_file.is_file() or html_file.is_symlink():
            continue
        try:
            content = html_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        def replace_url(match: re.Match) -> str:
            url = match.group("url")
            if url.startswith(access_path):
                return match.group(0)
            rewritten_url = f"{access_path.rstrip('/')}{url}"
            return (
                f"{match.group('prefix')}{rewritten_url}{match.group('quote')}"
            )

        rewritten = _ROOT_RELATIVE_HTML_URL.sub(replace_url, content)
        if rewritten == content:
            continue
        html_file.write_text(rewritten, encoding="utf-8")
        rewritten_files.append(str(html_file.relative_to(target_dir)))

    return rewritten_files
