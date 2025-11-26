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

  // 获取编译日志
  getBuildLog(version) {
    return api.get(`/nginx/versions/${encodeURIComponent(version)}/build_log`)
  }
}


