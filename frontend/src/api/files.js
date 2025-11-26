import api from './index'

export const filesApi = {
  // 列出文件
  listFiles(path, version, rootOnly) {
    const params = {}
    if (path) params.path = path
    if (version) params.version = version
    if (rootOnly) params.root_only = rootOnly
    return api.get('/files', { params })
  },

  // 上传静态资源包（仅保存，不解压）
  uploadPackage(file) {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/files/upload-package', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // 列出已上传的静态资源包
  listPackages() {
    return api.get('/files/packages')
  },

  // 删除已上传的静态资源包
  deletePackage(filename) {
    return api.delete(`/files/packages/${encodeURIComponent(filename)}`)
  },

  // 部署静态资源包（使用已上传的文件或新上传的文件）
  deployPackage(filename, file, version, extractToSubdir) {
    const formData = new FormData()
    if (filename) {
      formData.append('filename', filename)
    }
    if (file) {
      formData.append('file', file)
    }
    if (version) {
      formData.append('version', version)
    }
    formData.append('extract_to_subdir', extractToSubdir)
    return api.post('/files/deploy-package', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // 获取文件内容
  getFile(path, version) {
    const params = {}
    if (version) params.version = version
    return api.get(`/files/${encodeURIComponent(path)}`, { params })
  },

  // 上传文件
  uploadFile(path, files, version) {
    const formData = new FormData()
    if (path) {
      formData.append('path', path)
    }
    if (version) {
      formData.append('version', version)
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
  updateFile(path, content, version) {
    const formData = new FormData()
    formData.append('content', content)
    if (version) {
      formData.append('version', version)
    }
    return api.put(`/files/${encodeURIComponent(path)}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // 删除文件
  deleteFile(path, version) {
    const params = {}
    if (version) params.version = version
    return api.delete(`/files/${encodeURIComponent(path)}`, { params })
  },

  // 创建目录
  createDirectory(path, name, version) {
    const formData = new FormData()
    if (path) {
      formData.append('path', path)
    }
    if (version) {
      formData.append('version', version)
    }
    formData.append('name', name)
    return api.post('/files/mkdir', formData)
  },

  // 重命名文件
  renameFile(path, newName, version) {
    const formData = new FormData()
    formData.append('new_name', newName)
    if (version) {
      formData.append('version', version)
    }
    return api.post(`/files/rename/${encodeURIComponent(path)}`, formData)
  },

  // 下载文件
  downloadFile(path, version) {
    const params = {}
    if (version) params.version = version
    return api.get(`/files/download/${encodeURIComponent(path)}`, {
      params,
      responseType: 'blob'
    })
  }
}

