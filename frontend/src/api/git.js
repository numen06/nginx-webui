import api from './index'

export const gitApi = {
  getConfig() {
    return api.get('/git/config')
  },
  saveConfig(payload) {
    return api.post('/git/config', payload)
  },
  sync() {
    return api.post('/git/sync')
  }
}

