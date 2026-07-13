# 默认 Nginx 源码包目录

- **Docker 镜像**：构建阶段通过根目录 `Dockerfile` 的 `COPY backend/ /app/backend/`，将仓库内置的 `nginx-1.31.2.tar.gz` 一并复制到镜像，不再联网重复下载；容器首次启动时由后端检测 `versions/last` 是否存在，若不存在则自动编译并同步到 `last`。
- **本地开发**：可手动将官方 `nginx-*.tar.gz` / `.tgz` 放到本目录；优先使用 `nginx-1.31.2.tar.gz`，否则取目录中版本号最高的源码包（见 `app/routers/nginx_manager.py` 中 `_get_default_nginx_tar_path`）。
