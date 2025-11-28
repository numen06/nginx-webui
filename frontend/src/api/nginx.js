import api from './index'

export const nginxApi = {
  // 获取已安装版本列表
  listVersions() {
    return api.get('/nginx/versions')
  },

  // 获取 Nginx 官方最新版本列表
  getLatestVersions(limit = 5) {
    return api.get('/nginx/versions/latest', {
      params: { limit }
    })
  },

  // 获取单个版本状态
  getVersionStatus(version) {
    return api.get(`/nginx/versions/${encodeURIComponent(version)}/status`)
  },

  // 检查下载地址是否可以访问
  checkDownloadUrl(url) {
    return api.post('/nginx/versions/download/check-url', {
      url: url
    })
  },

  // 获取下载进度
  getDownloadProgress(version) {
    return api.get(`/nginx/versions/download/progress/${encodeURIComponent(version)}`)
  },

  // 在线下载 Nginx 源码包（不编译）
  downloadAndBuild(payload) {
    return api.post('/nginx/versions/download', payload)
  },

  // 上传 Nginx 源码包（不编译）
  uploadAndBuild(formData, onUploadProgress) {
    return api.post('/nginx/versions/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress
    })
  },

  // 编译指定版本（基于已下载/上传的源码包）
  compileVersion(version) {
    return api.post(`/nginx/versions/${encodeURIComponent(version)}/compile`)
  },

  // 将指定版本升级到运行版（last 目录）
  upgradeToProduction(version) {
    return api.post(`/nginx/versions/${encodeURIComponent(version)}/upgrade-to-production`)
  },

  // 启动指定版本
  startVersion(version) {
    return api.post(`/nginx/versions/${encodeURIComponent(version)}/start`)
  },

  // 停止指定版本
  stopVersion(version) {
    return api.post(`/nginx/versions/${encodeURIComponent(version)}/stop`)
  },

  // 强制停止指定版本
  forceStopVersion(version) {
    return api.post(`/nginx/versions/${encodeURIComponent(version)}/force_stop`)
  },

  // 强制释放 HTTP 端口（默认 80）
  forceReleaseHttpPort(port = 80) {
    return api.post('/nginx/force_release_http_port', null, {
      params: { port }
    })
  },

  // 删除指定版本（仅在未运行状态下允许）
  deleteVersion(version) {
    return api.delete(`/nginx/versions/${encodeURIComponent(version)}`)
  },

  // 获取编译日志
  getBuildLog(version) {
    return api.get(`/nginx/versions/${encodeURIComponent(version)}/build_log`)
  }
}


