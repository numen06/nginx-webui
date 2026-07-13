import api from './index'

export const auditApi = {
  // 获取操作日志
  getLogs(params) {
    return api.get('/audit/logs', { params })
  },

  // 清理操作日志
  cleanupLogs(payload) {
    return api.post('/audit/logs/cleanup', payload)
  }
}

