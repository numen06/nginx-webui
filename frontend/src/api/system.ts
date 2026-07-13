import api from './index'

export interface SystemResourcesResponse {
  success: boolean
  cpu: { percent?: number; count?: { physical?: number; logical?: number } }
  memory: { total?: number; used?: number; available?: number; percent?: number }
  disk: { root?: { total?: number; used?: number; free?: number; percent?: number } }
  network: { connections?: number; bytes_sent?: number; bytes_recv?: number }
  system: Record<string, unknown>
}

export const systemApi = {
  // 获取系统资源信息
  getResources() {
    return api.get<SystemResourcesResponse>('/system/resources')
  },

  // 获取系统版本信息
  getVersion() {
    return api.get('/system/version')
  },

  // 检查系统更新
  checkUpdate() {
    return api.get('/system/version/check-update')
  }
}
