import api from './index'

export const statisticsApi = {
  // 获取统计概览
  getOverview(hours = 24) {
    return api.get('/statistics/overview', {
      params: { hours }
    })
  },

  // 获取实时统计数据
  getRealtime() {
    return api.get('/statistics/realtime')
  }
}

