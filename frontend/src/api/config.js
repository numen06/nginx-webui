import api from './index'

export const configApi = {
  // 获取配置
  getConfig() {
    return api.get('/config')
  },

  // 更新配置
  updateConfig(content) {
    return api.post('/config', { content })
  },

  // 测试配置
  testConfig() {
    return api.post('/config/test')
  },

  // 重载配置
  reloadConfig() {
    return api.post('/config/reload')
  },

  // 获取状态
  getStatus() {
    return api.get('/config/status')
  },

  // 获取备份列表
  getBackups() {
    return api.get('/config/backups')
  },

  // 创建备份
  createBackup() {
    return api.post('/config/backup')
  },

  // 恢复备份
  restoreBackup(backupId) {
    return api.post(`/config/restore/${backupId}`)
  }
}

