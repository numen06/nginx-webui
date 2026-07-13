import { defineStore } from 'pinia'
import { authApi, type User } from '@/api/auth'
import { apiErrorMessage } from '@/api'

interface LoginResult {
  success: boolean
  isDefaultPassword?: boolean
  message?: string
}

let userRequest: Promise<User | null> | null = null

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') as string | null,
    user: null as User | null,
  }),

  getters: {
    isAuthenticated: state => Boolean(state.token),
    username: state => state.user?.username || null,
    isAdmin: state => Boolean(state.user?.is_admin),
  },

  actions: {
    setToken(token: string) {
      this.token = token
      localStorage.setItem('token', token)
    },

    setUser(user: User | null) {
      this.user = user
    },

    async login(username: string, password: string): Promise<LoginResult> {
      try {
        const response = await authApi.login(username, password)
        if (!response.access_token) return { success: false, message: '登录响应格式错误' }
        this.setToken(response.access_token)
        const user = await this.ensureUser(true)
        return {
          success: Boolean(user),
          isDefaultPassword: Boolean(user?.is_default_password),
        }
      } catch (error) {
        this.logout()
        return {
          success: false,
          message: apiErrorMessage(error, '登录失败，请检查用户名和密码'),
        }
      }
    },

    async ensureUser(force = false): Promise<User | null> {
      if (this.user && !force) return this.user
      if (!this.token) return null
      if (!userRequest) {
        userRequest = authApi.getCurrentUser()
          .then(response => {
            this.user = response.user
            return response.user
          })
          .catch(() => {
            this.logout()
            return null
          })
          .finally(() => { userRequest = null })
      }
      return userRequest
    },

    async fetchUserInfo() {
      await this.ensureUser(true)
    },

    logout() {
      this.token = null
      this.user = null
      localStorage.removeItem('token')
    },
  },
})
