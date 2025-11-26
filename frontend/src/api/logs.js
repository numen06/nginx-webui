import api from './index'

export const logsApi = {
  // 获取访问日志
  getAccessLogs(page = 1, pageSize = 100) {
    return api.get('/logs/access', { params: { page, page_size: pageSize } })
  },

  // 获取错误日志
  getErrorLogs(page = 1, pageSize = 100) {
    return api.get('/logs/error', { params: { page, page_size: pageSize } })
  }
}

