import api from './index'

export const dynamicServicesApi = {
  list() {
    return api.get('/dynamic-services')
  },

  getAuthStatus() {
    return api.get('/dynamic-services/auth-status')
  },

  updateSettings(data) {
    return api.put('/dynamic-services/settings', data)
  },

  getGeneratedConfig() {
    return api.get('/dynamic-services/generated-config')
  },

  create(data) {
    return api.post('/dynamic-services', data)
  },

  update(serviceId, data) {
    return api.put(`/dynamic-services/service/${serviceId}`, data)
  },

  setEnabled(serviceId, enabled) {
    return api.post(`/dynamic-services/service/${serviceId}/enable`, { enabled })
  },

  delete(serviceId) {
    return api.delete(`/dynamic-services/service/${serviceId}`)
  },

  offlineInstance(serviceId, instanceId) {
    return api.post(`/dynamic-services/service/${serviceId}/instances/${encodeURIComponent(instanceId)}/offline`)
  }
}
