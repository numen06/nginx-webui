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
    // 确保返回的是对象，如果后端返回字符串则尝试解析
    const data = response.data
    if (typeof data === 'string') {
      try {
        return JSON.parse(data)
      } catch (e) {
        // 如果无法解析，返回包装后的对象
        return { message: data, raw: data }
      }
    }
    return data
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
      let errorData = error.response.data
      
      // 如果 errorData 是字符串，尝试解析或创建对象
      if (typeof errorData === 'string') {
        try {
          errorData = JSON.parse(errorData)
        } catch (e) {
          // 解析失败，创建一个对象包装字符串
          errorData = { detail: errorData, message: errorData }
        }
      }
      
      // 如果 errorData 不存在或不是对象，创建一个默认对象
      if (!errorData || typeof errorData !== 'object' || Array.isArray(errorData)) {
        errorData = { 
          detail: errorData ? String(errorData) : `请求失败 (${error.response.status})`,
          message: errorData ? String(errorData) : `请求失败 (${error.response.status})`
        }
      }
      
      // 安全地展开 errorData，只复制字符串和基本类型的属性
      const errorObj = {
        status: error.response.status,
        statusText: error.response.statusText,
        detail: (errorData.detail && typeof errorData.detail === 'string') 
          ? errorData.detail 
          : (errorData.message && typeof errorData.message === 'string')
            ? errorData.message
            : `请求失败 (${error.response.status})`
      }
      
      // 安全地复制其他属性（只复制字符串、数字、布尔值）
      for (const key in errorData) {
        if (errorData.hasOwnProperty(key) && 
            (typeof errorData[key] === 'string' || 
             typeof errorData[key] === 'number' || 
             typeof errorData[key] === 'boolean' ||
             errorData[key] === null)) {
          errorObj[key] = errorData[key]
        }
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

