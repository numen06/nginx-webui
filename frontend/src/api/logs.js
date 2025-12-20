import api from './index'

export const logsApi = {
  // 获取访问日志
  getAccessLogs(page = 1, pageSize = 100, keyword = null, startDate = null, endDate = null, rotateFile = null) {
    const params = { page, page_size: pageSize }
    if (keyword) params.keyword = keyword
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    if (rotateFile) params.rotate_file = rotateFile
    return api.get('/logs/access', { params })
  },

  // 获取错误日志
  getErrorLogs(page = 1, pageSize = 100, keyword = null, startDate = null, endDate = null, rotateFile = null) {
    const params = { page, page_size: pageSize }
    if (keyword) params.keyword = keyword
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    if (rotateFile) params.rotate_file = rotateFile
    return api.get('/logs/error', { params })
  },

  // 获取日志轮转状态
  getLogRotateStatus() {
    return api.get('/logs/rotate/status')
  },

  // 手动触发日志轮转
  triggerLogRotate() {
    return api.post('/logs/rotate')
  },

  // 获取日志分片文件列表
  getLogRotateFiles() {
    return api.get('/logs/rotate/files')
  },

  // 删除日志分片文件
  deleteLogRotateFile(filename) {
    return api.delete(`/logs/rotate/file/${encodeURIComponent(filename)}`)
  }
}

