import api from './index'

export const logsApi = {
  // 获取访问日志
  getAccessLogs(page = 1, pageSize = 100, keyword = null, startDate = null, endDate = null) {
    const params = { page, page_size: pageSize }
    if (keyword) params.keyword = keyword
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    return api.get('/logs/access', { params })
  },

  // 获取错误日志
  getErrorLogs(page = 1, pageSize = 100, keyword = null, startDate = null, endDate = null) {
    const params = { page, page_size: pageSize }
    if (keyword) params.keyword = keyword
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    return api.get('/logs/error', { params })
  }
}

