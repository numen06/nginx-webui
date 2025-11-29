import api from './index'

export const nginxApi = {
  // 获取已安装版本列表
  listVersions() {
    return api.get('/nginx/versions')
  },

  // 获取 Nginx 官方最新版本列表
  getLatestVersions(limit = 5) {
    return api.get('/nginx/versions/latest', {
      params: { limit }
    })
  },

  // 获取单个版本状态
  getVersionStatus(version) {
    return api.get(`/nginx/versions/${encodeURIComponent(version)}/status`)
  },

  // 检查下载地址是否可以访问
  checkDownloadUrl(url) {
    return api.post('/nginx/versions/download/check-url', {
      url: url
    })
  },

  // 获取下载进度
  getDownloadProgress(version) {
    return api.get(`/nginx/versions/download/progress/${encodeURIComponent(version)}`)
  },

  // 在线下载 Nginx 源码包（不编译）
  downloadAndBuild(payload) {
    return api.post('/nginx/versions/download', payload)
  },

  // 上传 Nginx 源码包（不编译）
  uploadAndBuild(formData, onUploadProgress) {
    return api.post('/nginx/versions/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress
    })
  },

  // 编译指定版本（基于已下载/上传的源码包，支持自定义参数和流式日志）
  compileVersion(version, customConfigureArgs = null, onLog = null) {
    return new Promise((resolve, reject) => {
      const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'
      const url = `${baseURL}/nginx/versions/${encodeURIComponent(version)}/compile`
      const body = JSON.stringify({ custom_configure_args: customConfigureArgs })
      const token = localStorage.getItem('token')
      
      fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: body
      }).then(response => {
        if (!response.ok) {
          return response.text().then(text => {
            try {
              const error = JSON.parse(text)
              throw new Error(error.detail || error.message || `HTTP error! status: ${response.status}`)
            } catch (e) {
              throw new Error(text || `HTTP error! status: ${response.status}`)
            }
          })
        }
        
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let hasSuccess = false
        let hasError = false
        
        function readStream() {
          reader.read().then(({ done, value }) => {
            if (done) {
              if (!hasSuccess && !hasError) {
                resolve({ success: true })
              }
              return
            }
            
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || '' // 保留最后一个不完整的行
            
            for (const line of lines) {
              if (line.trim() === '') continue
              
              if (line.startsWith('data: ')) {
                const data = line.slice(6) // 移除 'data: ' 前缀
                const decodedData = data.replace(/\\n/g, '\n').replace(/\\r/g, '\r').replace(/\\0/g, '')
                
                if (onLog) {
                  onLog(decodedData)
                }
                
                // 检查是否完成
                if (decodedData.includes('[SUCCESS]')) {
                  hasSuccess = true
                  setTimeout(() => {
                    resolve({ success: true })
                  }, 100)
                  reader.cancel()
                  return
                } else if (decodedData.includes('[ERROR]')) {
                  hasError = true
                  reject(new Error(decodedData))
                  reader.cancel()
                  return
                }
              }
            }
            
            readStream()
          }).catch(err => {
            if (!hasError) {
              reject(err)
            }
          })
        }
        
        readStream()
      }).catch(err => {
        reject(err)
      })
    })
  },

  // 将指定版本升级到运行版（last 目录）
  upgradeToProduction(version) {
    return api.post(`/nginx/versions/${encodeURIComponent(version)}/upgrade-to-production`)
  },

  // 启动指定版本
  startVersion(version) {
    return api.post(`/nginx/versions/${encodeURIComponent(version)}/start`)
  },

  // 停止指定版本
  stopVersion(version) {
    return api.post(`/nginx/versions/${encodeURIComponent(version)}/stop`)
  },

  // 强制停止指定版本
  forceStopVersion(version) {
    return api.post(`/nginx/versions/${encodeURIComponent(version)}/force_stop`)
  },

  // 强制释放Nginx端口（80和443）
  forceReleaseNginxPorts() {
    return api.post('/nginx/force_release_nginx_ports')
  },

  // 删除指定版本（仅在未运行状态下允许）
  deleteVersion(version) {
    return api.delete(`/nginx/versions/${encodeURIComponent(version)}`)
  },

  // 获取编译日志
  getBuildLog(version) {
    return api.get(`/nginx/versions/${encodeURIComponent(version)}/build_log`)
  },

  // 检查初始设置状态
  checkSetupStatus() {
    return api.get('/nginx/setup/check')
  },

  // 准备默认nginx压缩包
  prepareDefaultNginx() {
    return api.post('/nginx/setup/prepare-default')
  },

  // 获取编译进度
  getCompileProgress(version) {
    return api.get(`/nginx/versions/${encodeURIComponent(version)}/compile-progress`)
  },

  // 获取指定版本的 nginx.conf 配置内容
  getVersionConfig(version) {
    return api.get(`/nginx/versions/${encodeURIComponent(version)}/config`)
  }
}


