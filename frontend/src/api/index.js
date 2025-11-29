import axios from 'axios'

// 创建 axios 实例
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000
})

// 检查是否是nginx相关的API
const isNginxApi = (url) => {
  if (!url) return false
  return (
    url.includes('/nginx/') || 
    url.includes('/config') ||  // 包括 /config 和 /config/
    url.includes('/logs') ||    // 包括 /logs 和 /logs/
    url.includes('/files')      // 包括 /files 和 /files/
  )
}

// 请求拦截器 - 添加 token 和 Content-Type
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // 确保 JSON 请求设置正确的 Content-Type（如果还没有设置）
    if (config.data && !config.headers['Content-Type'] && !config.headers['content-type']) {
      // 如果是对象或数组，设置为 JSON
      if (typeof config.data === 'object' && !(config.data instanceof FormData)) {
        config.headers['Content-Type'] = 'application/json'
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器 - 处理错误
api.interceptors.response.use(
  async (response) => {
    // 确保返回的是对象，如果后端返回字符串则尝试解析
    const data = response.data
    let parsedData = data
    if (typeof data === 'string') {
      try {
        parsedData = JSON.parse(data)
      } catch (e) {
        // 如果无法解析，返回包装后的对象
        parsedData = { message: data, raw: data }
      }
    }
    
    // 检查响应中是否包含nginx相关的错误消息
    const responseText = typeof data === 'string' ? data : JSON.stringify(data)
    if (responseText && responseText.includes('未找到可用的 Nginx')) {
      // 如果是nginx相关的API，检查初始化状态
      const requestUrl = response.config?.url || ''
      if (isNginxApi(requestUrl) && !requestUrl.includes('/nginx/setup/')) {
        try {
          // 动态导入setupStore，避免循环依赖
          const { useSetupStore } = await import('../store/setup')
          const setupStore = useSetupStore()
          
          // 检查nginx初始化状态（强制检查）
          await setupStore.checkSetupStatus(true)
        } catch (setupError) {
          console.error('[API] 检查nginx设置状态失败:', setupError)
        }
      }
    }
    
    return parsedData
  },
  async (error) => {
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
        detail: null,
        data: errorData  // 保留原始数据，方便处理 422 等验证错误
      }
      
      // 处理 detail 字段（可能是字符串、对象或数组）
      if (errorData.detail) {
        if (typeof errorData.detail === 'string') {
          errorObj.detail = errorData.detail
        } else if (Array.isArray(errorData.detail)) {
          // 422 验证错误通常是数组格式
          errorObj.detail = errorData.detail
        } else if (typeof errorData.detail === 'object') {
          errorObj.detail = errorData.detail
        }
      }
      
      // 如果没有 detail，尝试使用 message
      if (!errorObj.detail) {
        errorObj.detail = (errorData.message && typeof errorData.message === 'string')
          ? errorData.message
          : `请求失败 (${error.response.status})`
      }
      
      // 安全地复制其他属性（只复制字符串、数字、布尔值）
      for (const key in errorData) {
        if (key !== 'detail' && key !== 'message' && errorData.hasOwnProperty(key) && 
            (typeof errorData[key] === 'string' || 
             typeof errorData[key] === 'number' || 
             typeof errorData[key] === 'boolean' ||
             errorData[key] === null ||
             Array.isArray(errorData[key]))) {
          errorObj[key] = errorData[key]
        }
      }
      
      // 如果是nginx相关的API调用失败，检查是否需要初始化
      const requestUrl = error.config?.url || ''
      const errorDetail = errorObj.detail || ''
      const errorText = typeof errorDetail === 'string' ? errorDetail : JSON.stringify(errorDetail)
      
      // 检查是否是nginx未初始化的错误（404或包含特定错误消息）
      const isNginxNotInitialized = (
        error.response.status === 404 || 
        errorText.includes('未找到可用的 Nginx') ||
        errorText.includes('未找到任何 Nginx')
      )
      
      const isNginxRelated = isNginxApi(requestUrl) && !requestUrl.includes('/nginx/setup/')
      
      console.log('[API拦截器] 检查nginx初始化:', {
        requestUrl,
        isNginxRelated,
        isNginxNotInitialized,
        status: error.response.status,
        errorText: errorText.substring(0, 100)
      })
      
      if (isNginxRelated && isNginxNotInitialized) {
        try {
          console.log('[API拦截器] 触发nginx初始化检查')
          // 动态导入setupStore，避免循环依赖
          const { useSetupStore } = await import('../store/setup')
          const setupStore = useSetupStore()
          
          // 检查nginx初始化状态（强制检查，因为可能nginx状态已改变）
          await setupStore.checkSetupStatus(true)
          console.log('[API拦截器] nginx初始化检查完成, showSetupWizard:', setupStore.showSetupWizard)
        } catch (setupError) {
          console.error('[API] 检查nginx设置状态失败:', setupError)
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

