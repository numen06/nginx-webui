<template>
  <div class="certificates-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <div>
            <span class="card-title">证书管理</span>
            <span class="card-subtitle">证书以域名为标识</span>
          </div>
          <div>
            <el-button type="primary" @click="handleRequest">
              <el-icon><DocumentAdd /></el-icon>
              <span class="btn-label">申请证书</span>
            </el-button>
            <el-button type="cyan" @click="handleUpload">
              <el-icon><UploadFilled /></el-icon>
              <span class="btn-label">上传证书</span>
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="certificateList" style="width: 100%">
        <el-table-column prop="domain" label="证书名称（域名）" width="200" fixed="left">
          <template #default="scope">
            <div class="domain-cell">
              <el-tag type="primary" size="small">{{ scope.row.domain }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="证书路径 / 私钥路径" min-width="600">
          <template #default="scope">
            <div class="paths-cell">
              <div class="path-item">
                <span class="path-label">证书：</span>
                <span class="path-text" :title="scope.row.cert_path || '-'">
                  {{ scope.row.cert_path || '-' }}
                </span>
                <el-tooltip content="复制证书路径" :show-after="200">
                  <el-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    :disabled="!scope.row.cert_path"
                    @click="handleCopy(scope.row.cert_path)"
                  />
                </el-tooltip>
              </div>
              <div class="path-item">
                <span class="path-label">私钥：</span>
                <span class="path-text" :title="scope.row.key_path || '-'">
                  {{ scope.row.key_path || '-' }}
                </span>
                <el-tooltip content="复制私钥路径" :show-after="200">
                  <el-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    :disabled="!scope.row.key_path"
                    @click="handleCopy(scope.row.key_path)"
                  />
                </el-tooltip>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="valid_to" label="过期时间" width="180" align="center">
          <template #default="scope">
            {{ formatDateTime(scope.row.valid_to) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" align="center">
          <template #default="scope">
            <div class="action-buttons">
              <el-tooltip content="重新上传" placement="top">
                <el-button
                  circle
                  size="small"
                  type="primary"
                  class="action-icon-btn"
                  @click="handleReupload(scope.row)"
                >
                  <el-icon><UploadFilled /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip content="续期" placement="top">
                <el-button
                  circle
                  size="small"
                  type="warning"
                  class="action-icon-btn"
                  @click="handleRenew(scope.row)"
                >
                  <el-icon><RefreshRight /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button
                  circle
                  size="small"
                  type="danger"
                  class="action-icon-btn"
                  @click="handleDelete(scope.row)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 上传证书对话框 -->
    <el-dialog
      v-model="uploadDialogVisible"
      :title="uploadForm.certId ? '重新上传证书' : '上传证书'"
      width="600px"
      top="8vh"
      :close-on-click-modal="false"
      class="cert-upload-dialog"
    >
      <el-form :model="uploadForm" :rules="uploadRules" ref="uploadFormRef" label-width="90px" class="compact-form">
        <el-form-item label="域名" prop="domain">
          <el-input 
            v-model="uploadForm.domain" 
            :placeholder="uploadForm.certId ? '重新上传将替换现有证书' : '例如：example.com'"
            :disabled="!!uploadForm.certId"
          />
          <div v-if="uploadForm.certId" class="form-tip">
            将替换域名 {{ uploadForm.domain }} 的现有证书和私钥
          </div>
        </el-form-item>
        
        <el-form-item label="上传方式">
          <el-radio-group v-model="uploadForm.mode" size="small">
            <el-radio-button label="files">文件上传</el-radio-button>
            <el-radio-button label="archive">压缩包</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 文件上传模式 -->
        <template v-if="uploadForm.mode === 'files'">
          <el-form-item label="证书文件" required>
            <el-upload
              ref="certUploadRef"
              :auto-upload="false"
              :limit="1"
              :on-change="handleCertFileChange"
              :on-remove="handleCertFileRemove"
              accept=".crt,.pem,.cer"
              :show-file-list="false"
            >
              <el-button size="small" type="primary">
                <el-icon><FolderOpened /></el-icon>
                选择证书
              </el-button>
            </el-upload>
            <div v-if="uploadForm.certFile" class="file-selected-compact">
              <span class="file-name-text">{{ uploadForm.certFile?.name || uploadForm.certFile?.raw?.name || '未知文件' }}</span>
              <el-button size="small" text type="danger" @click="handleCertFileRemove">×</el-button>
            </div>
            <div v-if="uploadForm.domain && uploadForm.certFile && !checkFileNameMatch(uploadForm.certFile?.name || uploadForm.certFile?.raw?.name, uploadForm.domain)" class="file-warning-compact">
              ⚠️ 文件名与域名不匹配
            </div>
          </el-form-item>
          <el-form-item label="私钥文件" required>
            <el-upload
              ref="keyUploadRef"
              :auto-upload="false"
              :limit="1"
              :on-change="handleKeyFileChange"
              :on-remove="handleKeyFileRemove"
              accept=".key,.pem"
              :show-file-list="false"
            >
              <el-button size="small" type="primary">
                <el-icon><FolderOpened /></el-icon>
                选择私钥
              </el-button>
            </el-upload>
            <div v-if="uploadForm.keyFile" class="file-selected-compact">
              <span class="file-name-text">{{ uploadForm.keyFile?.name || uploadForm.keyFile?.raw?.name || '未知文件' }}</span>
              <el-button size="small" text type="danger" @click="handleKeyFileRemove">×</el-button>
            </div>
            <div v-if="uploadForm.domain && uploadForm.keyFile && !checkFileNameMatch(uploadForm.keyFile?.name || uploadForm.keyFile?.raw?.name, uploadForm.domain)" class="file-warning-compact">
              ⚠️ 文件名与域名不匹配
            </div>
          </el-form-item>
        </template>

        <!-- 压缩包模式 -->
        <template v-else>
          <el-form-item label="压缩包" required>
            <el-upload
              ref="archiveUploadRef"
              :auto-upload="false"
              :limit="1"
              :on-change="handleArchiveFileChange"
              :on-remove="handleArchiveFileRemove"
              accept=".zip,.tar,.tar.gz,.tgz,.tar.bz2"
              :show-file-list="false"
            >
              <el-button size="small" type="primary">
                <el-icon><FolderOpened /></el-icon>
                选择压缩包
              </el-button>
            </el-upload>
            <div v-if="uploadForm.archiveFile" class="file-selected-compact">
              <span class="file-name-text">{{ uploadForm.archiveFile.name }}</span>
              <el-button size="small" text type="danger" @click="handleArchiveFileRemove">×</el-button>
            </div>
            <div class="upload-tip-small">支持 zip、tar.gz、tar.bz2 格式，自动识别证书与私钥</div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="uploadDialogVisible = false">
            <el-icon><CloseBold /></el-icon>
            <span class="btn-label">取消</span>
          </el-button>
            <el-button
              type="primary"
              :loading="uploading"
              :disabled="isUploadDisabled"
              @click="handleUploadSubmit"
            >
              <el-icon><Check /></el-icon>
              <span class="btn-label">{{ uploadForm.certId ? '更新' : '上传' }}</span>
            </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 手动复制对话框 -->
    <el-dialog
      v-model="copyTextDialogVisible"
      title="手动复制"
      width="600px"
    >
      <div style="margin-bottom: 12px; color: var(--el-text-color-regular);">
        复制失败，请手动选择并复制以下内容：
      </div>
      <el-input
        v-model="copyTextContent"
        type="textarea"
        :rows="4"
        readonly
        style="font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;"
      />
      <template #footer>
        <span class="dialog-footer">
          <el-button type="primary" @click="copyTextDialogVisible = false">
            <el-icon><Check /></el-icon>
            <span class="btn-label">已复制</span>
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { certificatesApi } from '../api/certificates'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentAdd, UploadFilled, RefreshRight, Delete, FolderOpened, CloseBold, Check, CopyDocument } from '@element-plus/icons-vue'
import { formatDateTime } from '../utils/date'

const certificateList = ref([])
const uploadDialogVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref(null)
const certUploadRef = ref(null)
const keyUploadRef = ref(null)
const archiveUploadRef = ref(null)
const copyTextDialogVisible = ref(false)
const copyTextContent = ref('')

const uploadForm = ref({
  domain: '',
  certFile: null,
  keyFile: null,
  archiveFile: null,
  mode: 'files',
  certId: null // 用于重新上传时标识要更新的证书ID
})

const isUploadDisabled = computed(() => {
  if (!uploadForm.value.domain) return true
  if (uploadForm.value.mode === 'archive') {
    return !uploadForm.value.archiveFile
  }
  return !uploadForm.value.certFile || !uploadForm.value.keyFile
})

const uploadRules = {
  domain: [
    { 
      required: true, 
      message: '请输入域名或上传压缩包自动识别', 
      trigger: 'blur',
      validator: (rule, value, callback) => {
        // 如果是压缩包模式，域名可以为空（后端会自动提取）
        if (uploadForm.value.mode === 'archive' && !value) {
          callback()
        } else if (!value) {
          callback(new Error('请输入域名'))
        } else if (!/^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$/.test(value)) {
          callback(new Error('请输入有效的域名'))
        } else {
          callback()
        }
      }
    }
  ]
}

const loadCertificates = async () => {
  try {
    const response = await certificatesApi.getCertificates()
    certificateList.value = response.certificates || []
  } catch (error) {
    ElMessage.error('加载证书列表失败')
  }
}

const handleRequest = () => {
  ElMessage.info('申请证书功能待实现')
}

const handleUpload = () => {
  uploadForm.value = {
    domain: '',
    certFile: null,
    keyFile: null,
    archiveFile: null,
    mode: 'files',
    certId: null
  }
  if (certUploadRef.value) {
    certUploadRef.value.clearFiles()
  }
  if (keyUploadRef.value) {
    keyUploadRef.value.clearFiles()
  }
  if (archiveUploadRef.value) {
    archiveUploadRef.value.clearFiles()
  }
  uploadDialogVisible.value = true
}

const handleReupload = (cert) => {
  uploadForm.value = {
    domain: cert.domain,
    certFile: null,
    keyFile: null,
    archiveFile: null,
    mode: 'files',
    certId: cert.id
  }
  if (certUploadRef.value) {
    certUploadRef.value.clearFiles()
  }
  if (keyUploadRef.value) {
    keyUploadRef.value.clearFiles()
  }
  if (archiveUploadRef.value) {
    archiveUploadRef.value.clearFiles()
  }
  uploadDialogVisible.value = true
}

const handleCertFileChange = (file) => {
  uploadForm.value.certFile = file.raw
}

const handleCertFileRemove = () => {
  uploadForm.value.certFile = null
  if (certUploadRef.value) {
    certUploadRef.value.clearFiles()
  }
}

const handleKeyFileChange = (file) => {
  uploadForm.value.keyFile = file.raw
}

const handleKeyFileRemove = () => {
  uploadForm.value.keyFile = null
  if (keyUploadRef.value) {
    keyUploadRef.value.clearFiles()
  }
}

const handleArchiveFileChange = async (file) => {
  uploadForm.value.archiveFile = file.raw
  
  // 自动解析压缩包中的域名
  if (file.raw) {
    try {
      const response = await certificatesApi.parseCertificateArchive(file.raw)
      if (response.domain) {
        uploadForm.value.domain = response.domain
        ElMessage.success(`已自动识别域名: ${response.domain}`)
      }
    } catch (error) {
      // 解析失败不影响用户手动输入域名
      console.warn('自动解析域名失败:', error)
    }
  }
}

const handleArchiveFileRemove = () => {
  uploadForm.value.archiveFile = null
  if (archiveUploadRef.value) {
    archiveUploadRef.value.clearFiles()
  }
}

// 检查文件名是否包含域名
const checkFileNameMatch = (fileName, domain) => {
  if (!fileName || !domain) return true
  try {
    // 移除文件扩展名和常见前缀后进行比较
    const nameWithoutExt = String(fileName).replace(/\.(crt|pem|cer|key)$/i, '').toLowerCase()
    const domainLower = String(domain).toLowerCase()
    // 检查文件名中是否包含域名
    return nameWithoutExt.includes(domainLower.replace(/\./g, '')) || 
           nameWithoutExt.includes(domainLower)
  } catch (error) {
    console.warn('检查文件名匹配时出错:', error)
    return true // 出错时默认返回true，不显示警告
  }
}

const handleUploadSubmit = async () => {
  if (!uploadFormRef.value) return
  
  try {
    await uploadFormRef.value.validate()
  } catch (error) {
    return
  }

  const mode = uploadForm.value.mode
  if (mode === 'archive') {
    if (!uploadForm.value.archiveFile) {
      ElMessage.warning('请选择包含证书与私钥的压缩包')
      return
    }
    // 压缩包模式下，如果没有域名，后端会尝试从证书中提取
  } else if (!uploadForm.value.certFile || !uploadForm.value.keyFile) {
    ElMessage.warning('请选择证书文件和私钥文件')
    return
  }

  uploading.value = true
  try {
    if (mode === 'archive') {
      await certificatesApi.uploadCertificateArchive(
        uploadForm.value.domain,
        uploadForm.value.archiveFile,
        false, // 手动上传的证书不支持自动续期
        uploadForm.value.certId
      )
      ElMessage.success(uploadForm.value.certId ? '证书更新成功' : '证书压缩包上传成功')
    } else {
    await certificatesApi.uploadCertificate(
      uploadForm.value.domain,
      uploadForm.value.certFile,
      uploadForm.value.keyFile,
      false, // 手动上传的证书不支持自动续期
      uploadForm.value.certId
    )
    ElMessage.success(uploadForm.value.certId ? '证书更新成功' : '证书上传成功')
    }
    uploadDialogVisible.value = false
    loadCertificates()
  } catch (error) {
    ElMessage.error(error.detail || error.message || '证书上传失败')
  } finally {
    uploading.value = false
  }
}

const handleRenew = async (cert) => {
  try {
    await certificatesApi.renewCertificate(cert.id)
    ElMessage.success('证书续期成功')
    loadCertificates()
  } catch (error) {
    ElMessage.error('证书续期失败')
  }
}

const handleDelete = async (cert) => {
  try {
    await ElMessageBox.confirm('确定要删除证书吗？', '提示', { type: 'warning' })
    await certificatesApi.deleteCertificate(cert.id)
    ElMessage.success('删除成功')
    loadCertificates()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleCopy = async (text) => {
  if (!text) return
  
  // 方法1: 尝试使用现代 Clipboard API
  if (navigator.clipboard && navigator.clipboard.writeText) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
      return
    } catch (error) {
      console.warn('Clipboard API 失败，尝试备用方法:', error)
    }
  }
  
  // 方法2: 使用传统的 execCommand 方法（备用）
  try {
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.position = 'fixed'
    textArea.style.left = '-999999px'
    textArea.style.top = '-999999px'
    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    
    const successful = document.execCommand('copy')
    document.body.removeChild(textArea)
    
    if (successful) {
      ElMessage.success('已复制到剪贴板')
      return
    }
  } catch (error) {
    console.warn('execCommand 方法失败:', error)
  }
  
  // 方法3: 如果都失败了，显示对话框让用户手动复制
  copyTextContent.value = text
  copyTextDialogVisible.value = true
}

onMounted(() => {
  loadCertificates()
})
</script>

<style scoped>
.certificates-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  margin-right: 12px;
}

.card-subtitle {
  font-size: 12px;
  color: #909399;
  font-weight: normal;
}

.file-name {
  margin-top: 8px;
  color: #606266;
  font-size: 12px;
}

.el-upload__tip {
  color: #909399;
  font-size: 12px;
  margin-top: 8px;
}

.paths-cell {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.path-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.path-label {
  font-size: 12px;
  color: #909399;
  font-weight: 500;
  min-width: 40px;
  flex-shrink: 0;
}

.path-text {
  flex: 1;
  font-size: 12px;
  color: #606266;
  word-break: break-all;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'source-code-pro', monospace;
  line-height: 1.6;
}

.domain-cell {
  display: flex;
  align-items: center;
}

.domain-cell :deep(.el-tag) {
  font-weight: 500;
  font-size: 13px;
}

.compact-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.compact-form :deep(.el-form-item__label) {
  font-size: 13px;
  padding-bottom: 4px;
}

.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}



.file-selected-compact {
  margin-top: 6px;
  padding: 6px 10px;
  background-color: var(--el-fill-color-lighter);
  border-radius: 4px;
  border: 1px solid var(--el-border-color-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.file-name-text {
  flex: 1;
  font-size: 12px;
  color: var(--el-text-color-primary);
  word-break: break-all;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
  line-height: 1.4;
}

.file-warning-compact {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-color-warning);
  line-height: 1.3;
}

.upload-tip-small {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  line-height: 1.3;
}

.action-buttons {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
}

.action-icon-btn {
  margin: 0;
}

.cert-upload-dialog :deep(.el-dialog__body) {
  max-height: calc(85vh - 120px);
  overflow-y: auto;
  padding: 20px;
}

.cert-upload-dialog :deep(.el-upload) {
  width: 100%;
}

.cert-upload-dialog :deep(.el-upload .el-button) {
  width: 100%;
}
</style>

