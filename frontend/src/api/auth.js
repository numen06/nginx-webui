import api from './index'

export const authApi = {
  // 登录
  login(username, password) {
    return api.post('/auth/login', { username, password })
  },

  // 获取当前用户信息
  getCurrentUser() {
    return api.get('/auth/me')
  }
}

