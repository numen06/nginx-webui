#!/bin/bash
set -euo pipefail

# 构建时预编译默认 Nginx，避免运行时再编译。
# 可通过环境变量覆盖默认值，便于后续维护。

NGINX_VERSION="${NGINX_VERSION:-1.29.3}"
SOURCE_TAR="${SOURCE_TAR:-/app/backend/default-nginx/nginx-${NGINX_VERSION}.tar.gz}"
BUILD_DIR="${BUILD_DIR:-/tmp/nginx-build}"
INSTALL_DIR="${INSTALL_DIR:-/app/data/nginx/versions/${NGINX_VERSION}}"

echo "[prebuild] NGINX_VERSION=${NGINX_VERSION}"
echo "[prebuild] SOURCE_TAR=${SOURCE_TAR}"
echo "[prebuild] INSTALL_DIR=${INSTALL_DIR}"

if [ ! -f "${SOURCE_TAR}" ]; then
  echo "[prebuild] ERROR: source tar not found: ${SOURCE_TAR}" >&2
  exit 1
fi

mkdir -p /app/data/nginx/versions /app/data/nginx/build_logs
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

tar -xzf "${SOURCE_TAR}" -C "${BUILD_DIR}"
SRC_DIR="$(ls -d "${BUILD_DIR}"/* | head -n 1)"

if [ -z "${SRC_DIR}" ] || [ ! -d "${SRC_DIR}" ]; then
  echo "[prebuild] ERROR: source directory not found after extract" >&2
  exit 1
fi

cd "${SRC_DIR}"
./configure \
  --prefix="${INSTALL_DIR}" \
  --with-http_ssl_module \
  --with-http_realip_module \
  --with-http_addition_module \
  --with-http_sub_module \
  --with-http_dav_module \
  --with-http_flv_module \
  --with-http_mp4_module \
  --with-http_gunzip_module \
  --with-http_gzip_static_module \
  --with-http_auth_request_module \
  --with-http_random_index_module \
  --with-http_secure_link_module \
  --with-http_degradation_module \
  --with-http_slice_module \
  --with-http_stub_status_module \
  --with-http_v2_module \
  --with-stream \
  --with-stream_ssl_module \
  --with-stream_realip_module \
  --with-stream_ssl_preread_module

make -j"$(nproc)"
make install

echo "${NGINX_VERSION}" > "${INSTALL_DIR}/.nginx-version"
echo "prebuilt" > "${INSTALL_DIR}/.prebuilt"

rm -rf "${BUILD_DIR}"
echo "[prebuild] done"
