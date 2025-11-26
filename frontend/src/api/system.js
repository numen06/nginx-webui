import api from './index'

export const systemApi = {
  // 获取系统资源信息
  getResources() {
    return api.get('/system/resources')
  }
}

