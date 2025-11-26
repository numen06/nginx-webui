<template>
  <div class="static-package-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>静态资源包管理</span>
          <div>
            <el-button type="primary" @click="uploadDialogVisible = true">
              上传并部署资源包
            </el-button>
          </div>
        </div>
      </template>

      <div class="version-info" v-if="selectedVersion">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="当前 Nginx 版本">
            <el-tag :type="currentVersionInfo?.running ? 'success' : 'info'">
              {{ selectedVersion }}
            </el-tag>
            <span v-if="currentVersionInfo?.running" class="running-badge">运行中</span>
          </el-descriptions-item>
          <el-descriptions-item label="HTML 目录">
            <el-text type="info" size="small">{{ htmlDirPath }}</el-text>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="upload-section">
        <el-alert
          title="使用说明"
          type="info"
          :closable="false"
          style="margin-bottom: 20px"
        >
          <template #default>
            <ul style="margin: 0; padding-left: 20px">
              <li>支持上传 .zip、.tar.gz、.tgz、.tar 格式的压缩包</li>
              <li>资源包将自动解压到当前 Nginx 版本的 html 目录</li>
              <li>可以选择解压到子目录（使用包名）或直接解压到 html 根目录</li>
              <li>建议在部署前先备份现有文件</li>
            </ul>
          </template>
        </el-alert>
      </div>
    </el-card>

    <!-- 上传对话框 -->
    <el-dialog
      v-model="uploadDialogVisible"
      title="上传并部署静态资源包"
      width="600px"
    >
      <el-form :model="uploadForm" label-width="140px">
        <el-form-item label="选择 Nginx 版本">
          <el-select
            v-model="uploadForm.version"
            placeholder="选择 Nginx 版本"
            style="width: 100%"
          >
            <el-option
              v-for="version in versions"
              :key="version.version"
              :label="`${version.version}${version.running ? ' (运行中)' : ''}`"
              :value="version.version"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="资源包文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :before-remove="() => !uploading"
            accept=".zip,.tar.gz,.tgz,.tar"
          >
            <el-button type="primary">选择文件</el-button>
            <template #tip>
              <div class="el-upload__tip">
                支持 .zip、.tar.gz、.tgz、.tar 格式
              </div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="解压选项">
          <el-radio-group v-model="uploadForm.extractToSubdir">
            <el-radio :label="false">直接解压到 html 根目录</el-radio>
            <el-radio :label="true">解压到子目录（使用包名）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="uploadDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="uploading"
            :disabled="!selectedFile"
            @click="handleDeploy"
          >
            部署
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { filesApi } from '../api/files'
import { nginxApi } from '../api/nginx'
import { ElMessage } from 'element-plus'

const versions = ref([])
const selectedVersion = ref(null)
const uploadDialogVisible = ref(false)
const uploadForm = ref({
  version: null,
  extractToSubdir: false
})
const selectedFile = ref(null)
const uploading = ref(false)
const uploadRef = ref(null)

const currentVersionInfo = computed(() => {
  return versions.value.find(v => v.version === selectedVersion.value)
})

const htmlDirPath = computed(() => {
  if (currentVersionInfo.value) {
    return `${currentVersionInfo.value.install_path}/html`
  }
  return '-'
})

const loadVersions = async () => {
  try {
    const data = await nginxApi.listVersions()
    versions.value = data || []
    // 默认选择运行中的版本，如果没有则选择第一个已编译的版本
    if (versions.value.length > 0) {
      const running = versions.value.find(v => v.running && v.compiled)
      if (running) {
        selectedVersion.value = running.version
        uploadForm.value.version = running.version
      } else {
        const compiled = versions.value.find(v => v.compiled)
        if (compiled) {
          selectedVersion.value = compiled.version
          uploadForm.value.version = compiled.version
        } else {
          selectedVersion.value = versions.value[0].version
          uploadForm.value.version = versions.value[0].version
        }
      }
    }
  } catch (error) {
    console.error('加载版本列表失败:', error)
  }
}

const handleFileChange = (file) => {
  selectedFile.value = file.raw
}

const handleDeploy = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择资源包文件')
    return
  }
  if (!uploadForm.value.version) {
    ElMessage.warning('请先选择 Nginx 版本')
    return
  }

  uploading.value = true
  try {
    const res = await filesApi.deployPackage(
      selectedFile.value,
      uploadForm.value.version,
      uploadForm.value.extractToSubdir
    )
    ElMessage.success(res.message || '部署成功')
    uploadDialogVisible.value = false
    // 重置
    if (uploadRef.value) {
      uploadRef.value.clearFiles()
    }
    selectedFile.value = null
  } catch (error) {
    ElMessage.error(error.detail || '部署失败')
  } finally {
    uploading.value = false
  }
}

onMounted(() => {
  loadVersions()
})
</script>

<style scoped>
.static-package-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.version-info {
  margin-bottom: 20px;
}

.running-badge {
  margin-left: 8px;
  font-size: 12px;
  color: var(--nginx-green);
}

.upload-section {
  margin-top: 20px;
}
</style>

