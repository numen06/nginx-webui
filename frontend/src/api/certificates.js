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

  /** 下载证书与私钥（ZIP） */
  downloadCertificateBundle(certId) {
    return api.get(`/certificates/${certId}/download`, {
      responseType: 'blob'
    })
  },

  /** 列出本机 /etc/letsencrypt/live 下可导出的证书目录名 */
  listLetsencryptLiveDomains() {
    return api.get('/certificates/letsencrypt-live/list')
  },

  /**
   * 一键导出：固定扫描 /etc/letsencrypt/live/，默认导出字母序第一本（ZIP）
   */
  exportLetsencryptLiveAuto() {
    return api.get('/certificates/letsencrypt-live/export-auto', {
      responseType: 'blob'
    })
  },

  /**
   * 指定 live 子目录名导出（多本证书时需非默认项时使用）
   */
  exportLetsencryptLiveBundle(domain) {
    return api.get('/certificates/letsencrypt-live/export', {
      params: { domain },
      responseType: 'blob'
    })
  },

  // 上传证书（如果提供certId，则更新现有证书）
  uploadCertificate(domain, certFile, keyFile, autoRenew, certId = null) {
    const formData = new FormData()
    formData.append('domain', domain)
    formData.append('cert_file', certFile)
    formData.append('key_file', keyFile)
    formData.append('auto_renew', autoRenew)
    if (certId) {
      formData.append('cert_id', certId)
    }
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

  // 上传压缩包并自动解析证书（如果提供certId，则更新现有证书）
  uploadCertificateArchive(domain, archiveFile, autoRenew, certId = null) {
    const formData = new FormData()
    if (domain) {
      formData.append('domain', domain)
    }
    formData.append('archive_file', archiveFile)
    formData.append('auto_renew', autoRenew)
    if (certId) {
      formData.append('cert_id', certId)
    }
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

  /** 查询是否有未完成的 DNS 验证（同一会话下记录值不变） */
  dnsChallengePending(domain) {
    return api.get('/certificates/dns-challenge/pending', {
      params: { domain }
    })
  },

  /** DNS 验证：启动 certbot 并获取 TXT */
  dnsChallengeStart(domain, email) {
    return api.post('/certificates/dns-challenge/start', { domain, email })
  },

  /** DNS 验证：TXT 生效后继续签发 */
  dnsChallengeComplete(jobId) {
    return api.post('/certificates/dns-challenge/complete', { job_id: jobId })
  },

  /** 检测公网 DNS TXT（可能多次查询，单独放宽超时） */
  verifyDns(recordName, recordValue) {
    return api.post(
      '/certificates/verify-dns',
      {
        record_name: recordName,
        record_value: recordValue
      },
      { timeout: 90000 }
    )
  },

  /** 校验证书文件（openssl） */
  verifyCert(certId) {
    return api.post('/certificates/verify-cert', { cert_id: certId })
  },

  /** 检测自动续签环境（certbot renew --dry-run，不修改真实证书） */
  testAutoRenewEnvironment() {
    return api.post('/certificates/test-auto-renew-env', {}, { timeout: 360000 })
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

