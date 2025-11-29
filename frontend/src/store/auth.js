import { defineStore } from 'pinia'
import { authApi } from '../api/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null,
    user: null
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
    username: (state) => state.user?.username || null
  },

  actions: {
    setToken(token) {
      this.token = token
      localStorage.setItem('token', token)
    },

    setUser(user) {
      this.user = user
    },

    async login(username, password) {
      try {
        const response = await authApi.login(username, password)
        if (response.access_token) {
          this.setToken(response.access_token)
          
          // 获取用户信息
          const userInfo = await authApi.getCurrentUser()
          this.setUser(userInfo.user)
          
          return { 
            success: true,
            isDefaultPassword: userInfo.user?.is_default_password || false
          }
        } else {
          return {
            success: false,
            message: '登录响应格式错误'
          }
        }
      } catch (error) {
        console.error('登录错误:', error)
        const errorMessage = error?.detail || error?.message || error?.response?.data?.detail || '登录失败，请检查用户名和密码'
        return {
          success: false,
          message: errorMessage
        }
      }
    },

    async fetchUserInfo() {
      try {
        const response = await authApi.getCurrentUser()
        this.setUser(response.user)
      } catch (error) {
        console.error('获取用户信息失败:', error)
      }
    },

    logout() {
      this.token = null
      this.user = null
      localStorage.removeItem('token')
    }
  }
})

