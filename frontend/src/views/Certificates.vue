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
        <el-table-column label="操作" width="200" align="center">
          <template #default="scope">
            <el-button size="small" type="warning" @click="handleRenew(scope.row)">
              <el-icon><RefreshRight /></el-icon>
              <span class="btn-label">续期</span>
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">
              <el-icon><Delete /></el-icon>
              <span class="btn-label">删除</span>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 上传证书对话框 -->
    <el-dialog
      v-model="uploadDialogVisible"
      title="上传证书"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="uploadForm" :rules="uploadRules" ref="uploadFormRef" label-width="120px">
        <el-form-item label="域名" prop="domain">
          <el-input 
            v-model="uploadForm.domain" 
            placeholder="请输入域名，例如：example.com（压缩包上传后将自动识别）"
          />
        </el-form-item>
        <el-tabs v-model="uploadForm.mode" class="upload-tabs">
          <el-tab-pane label="证书 + 私钥" name="files">
        <el-form-item label="证书文件" required>
          <el-upload
            ref="certUploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleCertFileChange"
            :on-remove="handleCertFileRemove"
            accept=".crt,.pem,.cer"
          >
            <el-button type="primary">
              <el-icon><FolderOpened /></el-icon>
              <span class="btn-label">选择证书文件</span>
            </el-button>
            <template #tip>
              <div class="el-upload__tip">
                支持 .crt、.pem、.cer 格式
              </div>
            </template>
          </el-upload>
          <div v-if="uploadForm.certFile" class="file-name">
            已选择: {{ uploadForm.certFile.name }}
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
          >
            <el-button type="primary">
              <el-icon><FolderOpened /></el-icon>
              <span class="btn-label">选择私钥文件</span>
            </el-button>
            <template #tip>
              <div class="el-upload__tip">
                支持 .key、.pem 格式
              </div>
            </template>
          </el-upload>
          <div v-if="uploadForm.keyFile" class="file-name">
            已选择: {{ uploadForm.keyFile.name }}
          </div>
        </el-form-item>
          </el-tab-pane>
          <el-tab-pane label="压缩包自动解析" name="archive">
            <el-form-item label="压缩包文件" required>
              <el-upload
                ref="archiveUploadRef"
                :auto-upload="false"
                :limit="1"
                :on-change="handleArchiveFileChange"
                :on-remove="handleArchiveFileRemove"
                accept=".zip,.tar,.tar.gz,.tgz,.tar.bz2"
              >
                <el-button type="primary">
                  <el-icon><FolderOpened /></el-icon>
                  <span class="btn-label">选择压缩包</span>
                </el-button>
                <template #tip>
                  <div class="el-upload__tip">
                    支持 zip、tar.gz、tar.bz2 等常见压缩格式，系统将自动识别证书与私钥
                  </div>
                </template>
              </el-upload>
              <div v-if="uploadForm.archiveFile" class="file-name">
                已选择: {{ uploadForm.archiveFile.name }}
              </div>
            </el-form-item>
          </el-tab-pane>
        </el-tabs>
        <el-form-item label="自动续期">
          <el-switch v-model="uploadForm.autoRenew" />
        </el-form-item>
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
            <span class="btn-label">上传</span>
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

const uploadForm = ref({
  domain: '',
  certFile: null,
  keyFile: null,
  archiveFile: null,
  mode: 'files',
  autoRenew: false
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
    autoRenew: false
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
}

const handleKeyFileChange = (file) => {
  uploadForm.value.keyFile = file.raw
}

const handleKeyFileRemove = () => {
  uploadForm.value.keyFile = null
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
        uploadForm.value.autoRenew
      )
      ElMessage.success('证书压缩包上传成功')
    } else {
    await certificatesApi.uploadCertificate(
      uploadForm.value.domain,
      uploadForm.value.certFile,
      uploadForm.value.keyFile,
      uploadForm.value.autoRenew
    )
    ElMessage.success('证书上传成功')
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
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败，请手动复制')
  }
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

.upload-tabs {
  margin-top: 8px;
}

.upload-tabs :deep(.el-tabs__header) {
  margin-bottom: 20px;
}

.upload-tabs :deep(.el-tabs__item) {
  font-size: 14px;
  padding: 0 20px;
  height: 40px;
  line-height: 40px;
}

.upload-tabs :deep(.el-tabs__content) {
  padding: 0;
}
</style>

