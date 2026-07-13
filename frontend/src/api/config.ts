import api from './index'

export const configApi = {
  // 获取配置
  getConfig() {
    return api.get('/config')
  },

  // 配置目录树
  getTree() {
    return api.get('/config/tree')
  },

  // 获取配置文件
  getFile(path) {
    return api.get('/config/file', { params: { path } })
  },

  // 保存配置文件
  updateFile(path, content) {
    return api.put('/config/file', { path, content })
  },

  // 创建配置目录
  createDirectory(path, name) {
    return api.post('/config/mkdir', { path, name })
  },

  // 重命名配置文件或目录
  renamePath(path, newName) {
    return api.post('/config/rename', { path, new_name: newName })
  },

  // 删除配置文件或目录
  deletePath(path) {
    return api.delete('/config/file', { params: { path } })
  },

  // 测试配置
  testConfig() {
    return api.post('/config/test')
  },

  // 重载配置
  reloadConfig() {
    return api.post('/config/reload')
  },

  // 强制覆盖配置（不重载nginx）
  applyConfig() {
    return api.post('/config/apply')
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
  },

  // 格式化配置
  formatConfig(content) {
    return api.post('/config/format', { content })
  },

  validateFile(path, content) {
    return api.post('/config/validate', { path, content })
  },

  splitLegacyConfig() {
    return api.post('/config/split-legacy')
  },

  getMergedPreview() {
    return api.get('/config/merged-preview')
  }
}
