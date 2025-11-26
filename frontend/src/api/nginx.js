import api from './index'

export const nginxApi = {
  // 获取已安装版本列表
  listVersions() {
    return api.get('/nginx/versions')
  },

  // 获取单个版本状态
  getVersionStatus(version) {
    return api.get(`/nginx/versions/${encodeURIComponent(version)}/status`)
  },

  // 在线下载并编译
  downloadAndBuild(payload) {
    return api.post('/nginx/versions/download', payload)
  },

  // 上传源码包并编译
  uploadAndBuild(formData, onUploadProgress) {
    return api.post('/nginx/versions/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress
    })
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


