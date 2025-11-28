import api from './index'

export const certificatesApi = {
  // 获取证书列表
  getCertificates() {
    return api.get('/certificates')
  },

  // 获取证书详情
  getCertificate(certId) {
    return api.get(`/certificates/${certId}`)
  },

  // 上传证书
  uploadCertificate(domain, certFile, keyFile, autoRenew) {
    const formData = new FormData()
    formData.append('domain', domain)
    formData.append('cert_file', certFile)
    formData.append('key_file', keyFile)
    formData.append('auto_renew', autoRenew)
    return api.post('/certificates/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // 解析压缩包并提取域名（预览）
  parseCertificateArchive(archiveFile) {
    const formData = new FormData()
    formData.append('archive_file', archiveFile)
    return api.post('/certificates/parse-archive', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // 上传压缩包并自动解析证书
  uploadCertificateArchive(domain, archiveFile, autoRenew) {
    const formData = new FormData()
    if (domain) {
      formData.append('domain', domain)
    }
    formData.append('archive_file', archiveFile)
    formData.append('auto_renew', autoRenew)
    return api.post('/certificates/upload-archive', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // 申请证书
  requestCertificate(domains, email, validationMethod) {
    return api.post('/certificates/request', {
      domains,
      email,
      validation_method: validationMethod
    })
  },

  // 续期证书
  renewCertificate(certId) {
    return api.post(`/certificates/renew/${certId}`)
  },

  // 续期所有证书
  renewAllCertificates() {
    return api.post('/certificates/renew-all')
  },

  // 删除证书
  deleteCertificate(certId) {
    return api.delete(`/certificates/${certId}`)
  },

  // 更新证书信息
  updateCertificate(certId, autoRenew) {
    return api.put(`/certificates/${certId}`, { auto_renew: autoRenew })
  },

  // 检查证书过期时间
  checkExpiry() {
    return api.get('/certificates/check-expiry')
  }
}

