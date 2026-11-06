"""Apply the WebUI defaults to upstream Nginx source before compilation."""

import sys
from pathlib import Path


def hide_server_signature(source_dir: Path) -> None:
    """Suppress the generated Server header and error-page signature in off mode."""
    http = source_dir / "src" / "http"
    server_check = "if (r->headers_out.server == NULL) {"
    hidden_server_check = (
        "if (r->headers_out.server == NULL\n"
        "        && clcf->server_tokens != NGX_HTTP_SERVER_TOKENS_OFF)\n"
        "    {"
    )
    replacements = {
        "ngx_http_header_filter_module.c": (server_check, hidden_server_check, 2),
        "v2/ngx_http_v2_filter_module.c": (server_check, hidden_server_check, 2),
        "v3/ngx_http_v3_filter_module.c": (server_check, hidden_server_check, 2),
        "ngx_http_special_response.c": (
            'static u_char ngx_http_error_tail[] =\n"<hr><center>nginx</center>" CRLF\n',
            "static u_char ngx_http_error_tail[] =\n",
            1,
        ),
        "ngx_http_core_module.c": (
            "ngx_conf_merge_uint_value(conf->server_tokens, prev->server_tokens,\n"
            "                              NGX_HTTP_SERVER_TOKENS_ON);",
            "ngx_conf_merge_uint_value(conf->server_tokens, prev->server_tokens,\n"
            "                              NGX_HTTP_SERVER_TOKENS_OFF);",
            1,
        ),
    }

    updated = {}
    for relative_path, (old, new, count) in replacements.items():
        path = http / relative_path
        if relative_path.startswith(("v2/", "v3/")) and not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if content.count(old) == count:
            updated[path] = content.replace(old, new)
        elif content.count(new) != count:
            raise ValueError(f"无法隐藏 Nginx 服务标识，源码结构不匹配: {relative_path}")

    for path, content in updated.items():
        path.write_text(content, encoding="utf-8")

    # Only touch the sample pages shipped in the source archive.
    index = source_dir / "html" / "index.html"
    if index.is_file() and "<title>Welcome to nginx!</title>" in index.read_text(encoding="utf-8"):
        index.write_text(
            '<!doctype html>\n<html lang="en"><meta charset="utf-8">\n'
            "<title>Site is running</title><h1>Site is running</h1>\n</html>\n",
            encoding="utf-8",
        )
    error_page = source_dir / "html" / "50x.html"
    if error_page.is_file():
        content = error_page.read_text(encoding="utf-8")
        neutral = content.replace("<p><em>Faithfully yours, nginx.</em></p>\n", "")
        if neutral != content:
            error_page.write_text(neutral, encoding="utf-8")


if __name__ == "__main__":
    hide_server_signature(Path(sys.argv[1]))
