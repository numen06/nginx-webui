<template>
  <div class="certificates-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>证书管理</span>
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
        <el-table-column prop="domain" label="域名" />
        <el-table-column prop="issuer" label="颁发者" />
        <el-table-column prop="valid_to" label="过期时间" width="180" />
        <el-table-column label="操作" width="200">
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
          <el-input v-model="uploadForm.domain" placeholder="请输入域名，例如：example.com" />
        </el-form-item>
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
            :disabled="!uploadForm.domain || !uploadForm.certFile || !uploadForm.keyFile"
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
import { ref, onMounted } from 'vue'
import { certificatesApi } from '../api/certificates'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentAdd, UploadFilled, RefreshRight, Delete, FolderOpened, CloseBold, Check } from '@element-plus/icons-vue'

const certificateList = ref([])
const uploadDialogVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref(null)
const certUploadRef = ref(null)
const keyUploadRef = ref(null)

const uploadForm = ref({
  domain: '',
  certFile: null,
  keyFile: null,
  autoRenew: false
})

const uploadRules = {
  domain: [
    { required: true, message: '请输入域名', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$/, message: '请输入有效的域名', trigger: 'blur' }
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
    autoRenew: false
  }
  if (certUploadRef.value) {
    certUploadRef.value.clearFiles()
  }
  if (keyUploadRef.value) {
    keyUploadRef.value.clearFiles()
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

const handleUploadSubmit = async () => {
  if (!uploadFormRef.value) return
  
  try {
    await uploadFormRef.value.validate()
  } catch (error) {
    return
  }

  if (!uploadForm.value.certFile || !uploadForm.value.keyFile) {
    ElMessage.warning('请选择证书文件和私钥文件')
    return
  }

  uploading.value = true
  try {
    await certificatesApi.uploadCertificate(
      uploadForm.value.domain,
      uploadForm.value.certFile,
      uploadForm.value.keyFile,
      uploadForm.value.autoRenew
    )
    ElMessage.success('证书上传成功')
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
</style>

