# 默认 Nginx 源码包目录

- **Docker 镜像**：构建阶段会从 `https://nginx.org/download/` 下载 `nginx-<版本>.tar.gz` 到此目录（见根目录 `Dockerfile` 中的 `NGINX_DEFAULT_SOURCE_VERSION`），不在构建时编译；容器首次启动时由后端检测 `versions/last` 是否存在，若不存在则自动编译并同步到 `last`。
- **本地开发**：可手动将官方 `nginx-*.tar.gz` / `.tgz` 放到本目录；优先使用 `nginx-1.31.2.tar.gz`，否则取目录中版本号最高的源码包（见 `app/routers/nginx_manager.py` 中 `_get_default_nginx_tar_path`）。
