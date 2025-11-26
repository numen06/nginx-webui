import api from './index'

export const filesApi = {
  // 列出文件
  listFiles(path) {
    return api.get('/files', { params: { path } })
  },

  // 获取文件内容
  getFile(path) {
    return api.get(`/files/${encodeURIComponent(path)}`)
  },

  // 上传文件
  uploadFile(path, files) {
    const formData = new FormData()
    if (path) {
      formData.append('path', path)
    }
    files.forEach(file => {
      formData.append('files', file)
    })
    return api.post('/files/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // 更新文件
  updateFile(path, content) {
    const formData = new FormData()
    formData.append('content', content)
    return api.put(`/files/${encodeURIComponent(path)}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // 删除文件
  deleteFile(path) {
    return api.delete(`/files/${encodeURIComponent(path)}`)
  },

  // 创建目录
  createDirectory(path, name) {
    const formData = new FormData()
    if (path) {
      formData.append('path', path)
    }
    formData.append('name', name)
    return api.post('/files/mkdir', formData)
  },

  // 重命名文件
  renameFile(path, newName) {
    const formData = new FormData()
    formData.append('new_name', newName)
    return api.post(`/files/rename/${encodeURIComponent(path)}`, formData)
  },

  // 下载文件
  downloadFile(path) {
    return api.get(`/files/download/${encodeURIComponent(path)}`, {
      responseType: 'blob'
    })
  }
}

