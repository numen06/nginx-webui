---
name: Certbot自动证书配置（简化版）
overview: 增强 certbot 证书申请功能：certbot 使用默认路径申请证书，申请成功后自动复制证书文件到挂载的数据目录，并自动修改 nginx 配置文件添加 SSL 配置。
todos:
  - id: copy_cert_files
    content: 实现证书文件复制功能：从 certbot 默认路径 /etc/letsencrypt/live/{domain}/ 复制到项目 ssl_dir
    status: completed
  - id: parse_nginx_config
    content: 实现 nginx 配置解析功能：查找匹配域名的 server block（支持通配符）
    status: completed
  - id: add_ssl_config
    content: 实现在现有 server block 中添加 SSL 配置的功能（包含 HTTP 重定向）
    status: completed
    dependencies:
      - parse_nginx_config
  - id: create_ssl_server
    content: 实现创建新的 SSL server block 的功能（包含 HTTP 和 HTTPS 两个 block）
    status: completed
    dependencies:
      - parse_nginx_config
  - id: apply_ssl_auto
    content: 实现主函数：优先查找现有 server block，找不到则创建新的，保存到工作副本
    status: completed
    dependencies:
      - add_ssl_config
      - create_ssl_server
  - id: update_request_api
    content: 更新证书申请接口，集成自动复制和配置修改功能，更新数据库路径为复制后的路径
    status: completed
    dependencies:
      - copy_cert_files
      - apply_ssl_auto
isProject: false
---

# Certbot 自动证书配置功能（简化

版）

## 功能概述

在现有的 certbot 证书申请功能基础上，增加以下自动化功能：

1. **证书文件自动复制**：certbot 申请成功后，将证书文件从默认路径（`/etc/letsencrypt/live/{domain}/`）复制到项目的挂载目录（`ssl_dir`）
2. **nginx 配置自动修改**：自动查找或创建 server block，添加 SSL 配置

## 实现方案

### 1. 证书文件复制功能

在 `backend/app/utils/certbot.py` 中新增函数：

- `copy_certificate_files(domain: str) -> Dict[str, Any]`
- 从 certbot 默认路径 `/etc/letsencrypt/live/{domain}/fullchain.pem` 和 `privkey.pem` 复制证书文件
- 复制到项目的 `ssl_dir` 目录
- 证书文件命名为 `{domain}.crt`，私钥文件命名为 `{domain}.key`
- 处理文件不存在、权限错误等情况
- 返回复制后的文件路径

### 2. nginx 配置解析和修改功能

在 `backend/app/utils/nginx.py` 中新增函数：

- `find_server_block_by_domain(config_content: str, domain: str) -> Optional[Dict]`
- 解析 nginx 配置，查找匹配指定域名的 server block
- 支持精确匹配和通配符匹配（如 `*.example.com`）
- 返回 server block 的位置、内容和匹配的 server_name
- `add_ssl_to_server_block(config_content: str, server_block_info: Dict, cert_path: str, key_path: str) -> str`
- 在现有的 server block 中添加 SSL 配置
- 添加 `listen 443 ssl`、`ssl_certificate`、`ssl_certificate_key` 等配置
- 如果已有 `listen 80`，保持不变；如果没有，添加 `listen 80` 用于重定向
- 添加 HTTP 到 HTTPS 的重定向配置（如果不存在）
- `create_ssl_server_block(domain: str, cert_path: str, key_path: str, root_dir: str = None) -> Tuple[str, str]`
- 创建两个 server block：
  - HTTP server block（80端口）：重定向到 HTTPS
  - HTTPS server block（443端口）：SSL 配置和基本 location 配置
- 返回两个 server block 的配置字符串
- `apply_ssl_config(domain: str, cert_path: str, key_path: str) -> Dict[str, Any]`
- 主函数：优先查找现有 server block，找到则添加 SSL 配置；找不到则创建新的 server block
- 将修改后的配置保存到工作副本（使用 `save_config_content`）
- 返回操作结果和配置变更信息

### 3. 更新证书申请接口

修改 `backend/app/routers/certificates.py` 中的 `request_cert` 函数：

- 在证书申请成功后：

1. 调用 `copy_certificate_files(domain)` 从 certbot 默认路径复制证书文件到项目目录
2. 调用 `apply_ssl_config` 自动修改 nginx 配置
3. 更新数据库中的证书路径为复制后的路径（`ssl_dir/{domain}.crt` 和 `ssl_dir/{domain}.key`）
4. 记录操作日志

### 4. 配置解析工具

需要实现 nginx 配置解析功能：

- 使用正则表达式解析 server block
- 匹配 `server_name` 指令中的域名（支持多个域名、通配符）
- 处理嵌套的 server block 和注释
- 保持配置文件的格式和缩进

## 文件修改清单

1. **backend/app/utils/certbot.py**

- 新增 `copy_certificate_files` 函数（使用默认路径 `/etc/letsencrypt/live/{domain}/`）

1. **backend/app/utils/nginx.py**

- 新增 `find_server_block_by_domain` 函数
- 新增 `add_ssl_to_server_block` 函数
- 新增 `create_ssl_server_block` 函数
- 新增 `apply_ssl_config` 函数

1. **backend/app/routers/certificates.py**

- 修改 `request_cert` 函数，集成自动复制和配置修改功能

## Docker 环境考虑

1. **证书文件路径**：

- certbot 在容器内使用默认路径 `/etc/letsencrypt/live/{domain}/` 申请证书
- 申请成功后，复制到挂载的数据目录 `/app/data/ssl/`（对应宿主机的 `/opt/nginx-webui/data/ssl`）
- 这样即使容器重建，证书也不会丢失

1. **挂载卷配置**：

- docker-compose.yml 中已挂载 `/opt/nginx-webui/data:/app/data`
- ssl_dir 配置为 `../data/ssl`，会自动映射到挂载卷
- 无需额外配置

1. **权限处理**：

- 确保容器内的应用有权限读取 certbot 证书文件（`/etc/letsencrypt/live/`）
- 确保有权限写入项目的 `ssl_dir` 目录（`/app/data/ssl`）

## 注意事项

1. **配置文件格式**：需要正确处理 nginx 配置的格式（缩进、大括号等）
2. **错误处理**：文件复制失败、配置解析失败等情况需要妥善处理，返回详细的错误信息
3. **配置验证**：修改配置后需要验证配置的有效性（使用现有的 `test_config` 函数）
4. **备份机制**：修改配置前应该创建备份（已有备份机制）
5. **路径处理**：正确处理相对路径和绝对路径，特别是在 Docker 环境中
6. **证书路径**：数据库存储复制后的路径（`ssl_dir/{domain}.crt`），而不是 certbot 原始路径

## 测试要点

1. 证书文件复制功能测试（从 `/etc/letsencrypt/live/{domain}/` 复制到 `ssl_dir`）
2. 查找现有 server block 功能测试（精确匹配、通配符匹配）
3. 添加 SSL 配置到现有 server block 测试

