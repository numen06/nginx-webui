import axios from 'axios'

// 创建 axios 实例
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000
})

// 请求拦截器 - 添加 token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器 - 处理错误
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    console.error('API 请求错误:', error)
    
    if (error.response) {
      // 只有在非登录页面且是 401 错误时才跳转
      if (error.response.status === 401 && !window.location.pathname.includes('/login')) {
        // token 过期或无效，清除本地存储并跳转到登录页
        localStorage.removeItem('token')
        window.location.href = '/login'
      }
      // 返回错误信息，包含 detail 字段
      const errorData = error.response.data || {}
      const errorObj = {
        ...errorData,
        status: error.response.status,
        statusText: error.response.statusText,
        detail: errorData.detail || errorData.message || `请求失败 (${error.response.status})`
      }
      return Promise.reject(errorObj)
    } else if (error.request) {
      // 请求已发出但没有收到响应
      console.error('网络错误: 无法连接到服务器', error.request)
      const errorObj = {
        detail: '无法连接到服务器，请检查后端服务是否正在运行',
        message: '网络连接失败',
        code: 'NETWORK_ERROR'
      }
      return Promise.reject(errorObj)
    } else {
      // 其他错误
      console.error('请求配置错误:', error.message)
      const errorObj = {
        detail: error.message || '请求失败',
        message: '请求配置错误'
      }
      return Promise.reject(errorObj)
    }
  }
)

export default api

