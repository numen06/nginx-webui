<template>
  <div class="static-package-page page-shell">
    <ui-card>
      <template #header>
        <div class="card-header">
          <span>静态资源包管理</span>
        </div>
      </template>

      <div class="version-info" v-if="selectedDirectory">
        <ui-descriptions :column="2" border size="small">
          <ui-descriptions-item label="当前 Nginx 目录">
            <ui-text type="info" size="small">{{ selectedDirectory || '-' }}</ui-text>
          </ui-descriptions-item>
          <ui-descriptions-item label="当前 Nginx 版本">
            <template v-if="formatVersionLabel(currentVersionInfo)">
              <ui-tag type="info" size="small">
                {{ formatVersionLabel(currentVersionInfo) }}
              </ui-tag>
            </template>
            <span v-else style="color: var(--text-secondary)">未知</span>
          </ui-descriptions-item>
          <ui-descriptions-item v-if="currentVersionInfo?.running" label="运行状态">
            <ui-tag type="success" size="small">运行中</ui-tag>
          </ui-descriptions-item>
        </ui-descriptions>
      </div>


      <!-- 已上传资源包列表 -->
      <div class="packages-section">
        <div class="section-header">
          <div class="header-left">
            <h3>资源包列表</h3>
            <ui-text type="info" size="small" class="package-count">
              共 {{ packages.length }} 个资源包
            </ui-text>
          </div>
          <div class="header-right">
            <ui-button
              type="info"
              :icon="Refresh"
              @click="loadPackages"
              :loading="loadingPackages"
            >
              刷新
            </ui-button>
            <ui-button
              type="warning"
              :icon="Download"
              @click="extractDialogVisible = true"
            >
              提取资源包
            </ui-button>
            <ui-button
              type="cyan"
              :icon="Upload"
              @click="uploadDialogVisible = true"
            >
              上传资源包
            </ui-button>
          </div>
        </div>
        <ui-table
          :data="packages"
          v-loading="loadingPackages"
          style="width: 100%"
          empty-text="暂无资源包，请先上传"
          stripe
        >
          <ui-table-column label="文件名" min-width="250">
            <template #default="{ row }">
              <div class="filename-cell">
                <ui-icon class="file-icon"><Document /></ui-icon>
                <ui-text class="filename-text" :title="row.filename">
                  {{ row.filename }}
                </ui-text>
              </div>
            </template>
          </ui-table-column>
          <ui-table-column label="大小" width="120" align="right">
            <template #default="{ row }">
              <ui-text type="info">{{ formatFileSize(row.size) }}</ui-text>
            </template>
          </ui-table-column>
          <ui-table-column label="上传时间" width="180">
            <template #default="{ row }">
              <ui-text type="info" size="small">
                {{ formatTime(row.uploaded_time) }}
              </ui-text>
            </template>
          </ui-table-column>
          <ui-table-column label="操作" width="380" fixed="right" align="center">
            <template #default="{ row }">
              <div class="button-group justify-center">
                <ui-button
                  type="success"
                  size="small"
                  :icon="Promotion"
                  @click="handleDeployPackage(row.filename)"
                  :loading="deploying === row.filename"
                >
                  部署
                </ui-button>
                <ui-button
                  type="primary"
                  size="small"
                  :icon="Download"
                  @click="handleDownloadPackage(row.filename)"
                  :loading="downloading === row.filename"
                >
                  下载
                </ui-button>
                <ui-button
                  type="danger"
                  size="small"
                  :icon="Delete"
                  @click="handleDeletePackage(row.filename)"
                  :loading="deleting === row.filename"
                >
                  删除
                </ui-button>
              </div>
            </template>
          </ui-table-column>
        </ui-table>
      </div>
    </ui-card>

    <!-- 上传对话框 -->
    <ui-dialog
      v-model="uploadDialogVisible"
      title="上传静态资源包"
      width="600px"
      :close-on-click-modal="false"
    >
      <ui-form :model="uploadForm" label-width="140px">
        <ui-form-item label="资源包文件">
          <ui-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :before-remove="() => !uploading"
            accept=".zip,.tar.gz,.tgz,.tar"
          >
            <ui-button type="primary">
              <ui-icon><FolderOpened /></ui-icon>
              <span class="btn-label">选择文件</span>
            </ui-button>
            <template #tip>
              <div class="ui-upload__tip">
                支持 .zip、.tar.gz、.tgz、.tar 格式
              </div>
            </template>
          </ui-upload>
        </ui-form-item>
      </ui-form>
      <template #footer>
        <span class="dialog-footer">
          <ui-button type="info" @click="uploadDialogVisible = false">
            <ui-icon><CloseBold /></ui-icon>
            <span class="btn-label">取消</span>
          </ui-button>
          <ui-button
            type="primary"
            :loading="uploading"
            :disabled="!selectedFile"
            @click="handleUpload"
          >
            <ui-icon><UploadFilled /></ui-icon>
            <span class="btn-label">上传</span>
          </ui-button>
        </span>
      </template>
    </ui-dialog>

    <!-- 提取资源包对话框 -->
    <ui-dialog
      v-model="extractDialogVisible"
      title="提取静态资源包"
      width="600px"
      :close-on-click-modal="false"
    >
      <ui-form :model="extractForm" label-width="140px">
        <ui-form-item label="选择 Nginx 目录/版本">
          <ui-select
            v-model="extractForm.directory"
            placeholder="选择 Nginx 目录/版本"
            style="width: 100%"
          >
            <ui-option
              v-for="version in versions"
              :key="version.directory"
              :label="formatOptionLabel(version)"
              :value="version.directory"
            />
          </ui-select>
        </ui-form-item>
        <ui-alert
          title="说明"
          type="info"
          :closable="false"
          style="margin-bottom: 16px"
        >
          <template #default>
            将扫描静态文件夹（html目录）中的压缩包文件（.zip、.tar.gz、.tgz、.tar），
            并将它们提取到资源包存储目录。
          </template>
        </ui-alert>
        <ui-form-item label="提取选项">
          <ui-switch
            v-model="extractForm.deleteAfterExtract"
            active-text="提取后删除静态文件夹中的资源包"
            inactive-text="保留源文件"
          />
        </ui-form-item>
        <ui-alert
          v-if="extractForm.deleteAfterExtract"
          title="警告"
          type="warning"
          :closable="false"
          style="margin-top: 12px"
        >
          <template #default>
            提取后将删除静态文件夹（html目录）中的资源包文件，此操作不可恢复！
          </template>
        </ui-alert>
      </ui-form>
      <template #footer>
        <span class="dialog-footer">
          <ui-button type="info" @click="extractDialogVisible = false">
            <ui-icon><CloseBold /></ui-icon>
            <span class="btn-label">取消</span>
          </ui-button>
          <ui-button
            type="warning"
            :loading="extracting"
            :disabled="!extractForm.directory"
            @click="handleExtractConfirm"
          >
            <ui-icon><Download /></ui-icon>
            <span class="btn-label">确认提取</span>
          </ui-button>
        </span>
      </template>
    </ui-dialog>

    <!-- 部署对话框 -->
    <ui-dialog
      v-model="deployDialogVisible"
      title="部署静态资源包"
      width="600px"
      :close-on-click-modal="false"
    >
      <ui-form :model="deployForm" label-width="140px">
        <ui-form-item label="资源包">
          <ui-text>{{ deployForm.filename }}</ui-text>
        </ui-form-item>
        <ui-form-item label="选择 Nginx 目录/版本">
          <ui-select
            v-model="deployForm.directory"
            placeholder="选择 Nginx 目录/版本"
            style="width: 100%"
          >
            <ui-option
              v-for="version in versions"
              :key="version.directory"
              :label="formatOptionLabel(version)"
              :value="version.directory"
            />
          </ui-select>
        </ui-form-item>
        <ui-form-item label="解压选项">
          <ui-radio-group v-model="deployForm.extractToSubdir">
            <ui-radio :label="false">直接解压到 html 根目录</ui-radio>
            <ui-radio :label="true">解压到子目录（使用包名）</ui-radio>
          </ui-radio-group>
        </ui-form-item>
      </ui-form>
      <template #footer>
        <span class="dialog-footer">
          <ui-button type="info" @click="deployDialogVisible = false">
            <ui-icon><CloseBold /></ui-icon>
            <span class="btn-label">取消</span>
          </ui-button>
          <ui-button
            type="success"
            :loading="deploying"
            :disabled="!deployForm.directory"
            @click="handleDeployConfirm"
          >
            <ui-icon><CircleCheck /></ui-icon>
            <span class="btn-label">确认部署</span>
          </ui-button>
        </span>
      </template>
    </ui-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { filesApi } from '../api/files'
import { nginxApi } from '../api/nginx'
import { ElMessage, ElMessageBox } from '@/lib/feedback'
import { Refresh, Upload, Document, Promotion, Delete, FolderOpened, CloseBold, UploadFilled, CircleCheck, Download } from '@/components/icons'
import { formatDateTime } from '../utils/date'

const versions = ref([])
const selectedDirectory = ref(null)
const uploadDialogVisible = ref(false)
const deployDialogVisible = ref(false)
const extractDialogVisible = ref(false)
const uploadForm = ref({})
const deployForm = ref({
  filename: null,
  directory: null,
  extractToSubdir: false
})
const extractForm = ref({
  directory: null,
  deleteAfterExtract: false
})
const selectedFile = ref(null)
const uploading = ref(false)
const deploying = ref(null)
const deleting = ref(null)
const downloading = ref(null)
const extracting = ref(false)
const uploadRef = ref(null)
const packages = ref([])
const loadingPackages = ref(false)

const currentVersionInfo = computed(() => {
  return versions.value.find(v => v.directory === selectedDirectory.value)
})

const formatVersionLabel = (info) => {
  if (!info || typeof info !== 'object') return ''
  return info.version || ''
}

const formatOptionLabel = (info) => {
  if (!info) return '-'
  const versionLabel = formatVersionLabel(info)
  const directory = info.directory || ''
  const runningSuffix = info.running ? '（运行中）' : ''
  if (versionLabel && versionLabel !== directory) {
    return `${directory}（版本 ${versionLabel}）${runningSuffix}`
  }
  return `${directory || versionLabel || '未知'}${runningSuffix}`
}

const htmlDirPath = computed(() => {
  if (currentVersionInfo.value?.install_path) {
    return `${currentVersionInfo.value.install_path}/html`
  }
  return '-'
})

const loadVersions = async () => {
  try {
    const data = await nginxApi.listVersions()
    versions.value = data || []
    if (versions.value.length === 0) {
      selectedDirectory.value = null
      deployForm.value.directory = null
      return
    }

    if (selectedDirectory.value) {
      const stillExists = versions.value.some(v => v.directory === selectedDirectory.value)
      if (stillExists) {
        deployForm.value.directory = selectedDirectory.value
        extractForm.value.directory = selectedDirectory.value
        return
      }
    }

    const running = versions.value.find(v => v.running)
    if (running) {
      selectedDirectory.value = running.directory
      deployForm.value.directory = running.directory
      extractForm.value.directory = running.directory
      return
    }

    const compiled = versions.value.find(v => v.compiled)
    if (compiled) {
      selectedDirectory.value = compiled.directory
      deployForm.value.directory = compiled.directory
      extractForm.value.directory = compiled.directory
      return
    }

    selectedDirectory.value = versions.value[0].directory
    deployForm.value.directory = versions.value[0].directory
    extractForm.value.directory = versions.value[0].directory
  } catch (error) {
    console.error('加载版本列表失败:', error)
  }
}

const loadPackages = async () => {
  loadingPackages.value = true
  try {
    const res = await filesApi.listPackages()
    packages.value = res.packages || []
  } catch (error) {
    ElMessage.error(error.detail || '加载资源包列表失败')
  } finally {
    loadingPackages.value = false
  }
}

const handleFileChange = (file) => {
  selectedFile.value = file.raw
}

const handleUpload = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择资源包文件')
    return
  }

  uploading.value = true
  try {
    const res = await filesApi.uploadPackage(selectedFile.value)
    ElMessage.success(res.message || '上传成功')
    uploadDialogVisible.value = false
    // 重置
    if (uploadRef.value) {
      uploadRef.value.clearFiles()
    }
    selectedFile.value = null
    // 刷新列表
    await loadPackages()
  } catch (error) {
    ElMessage.error(error.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

const handleDeployPackage = (filename) => {
  deployForm.value.filename = filename
  deployForm.value.directory = selectedDirectory.value
  deployForm.value.extractToSubdir = false
  deployDialogVisible.value = true
}

const handleDeployConfirm = async () => {
  if (!deployForm.value.filename) {
    ElMessage.warning('请选择资源包')
    return
  }
  if (!deployForm.value.directory) {
    ElMessage.warning('请先选择 Nginx 目录/版本')
    return
  }

  deploying.value = deployForm.value.filename
  try {
    const res = await filesApi.deployPackage(
      deployForm.value.filename,
      null,
      deployForm.value.directory,
      deployForm.value.extractToSubdir
    )
    ElMessage.success(res.message || '部署成功')
    deployDialogVisible.value = false
  } catch (error) {
    ElMessage.error(error.detail || '部署失败')
  } finally {
    deploying.value = null
  }
}

const handleDownloadPackage = (filename) => {
  try {
    // 使用 URL 参数传递 token，浏览器会立即弹出保存对话框
    const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'
    const token = localStorage.getItem('token')
    let url = `${baseURL}/files/packages/download/${encodeURIComponent(filename)}`
    
    // 将 token 添加到 URL 参数中
    if (token) {
      url += `?token=${encodeURIComponent(token)}`
    }
    
    // 直接使用 a 标签下载，浏览器会立即弹出保存对话框
    const a = document.createElement('a')
    a.style.display = 'none'
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    
    ElMessage.success('开始下载')
  } catch (error) {
    ElMessage.error('下载失败')
    console.error('Download error:', error)
  }
}

const handleDeletePackage = async (filename) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除资源包 "${filename}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    deleting.value = filename
    try {
      const res = await filesApi.deletePackage(filename)
      ElMessage.success(res.message || '删除成功')
      await loadPackages()
    } catch (error) {
      ElMessage.error(error.detail || '删除失败')
    } finally {
      deleting.value = null
    }
  } catch {
    // 用户取消
  }
}

const handleExtractConfirm = async () => {
  if (!extractForm.value.directory) {
    ElMessage.warning('请先选择 Nginx 目录/版本')
    return
  }

  // 如果选择删除，需要二次确认
  if (extractForm.value.deleteAfterExtract) {
    try {
      await ElMessageBox.confirm(
        '确定要提取资源包并删除静态文件夹中的资源包文件吗？此操作不可恢复！',
        '确认提取',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )
    } catch {
      // 用户取消
      return
    }
  }

  extracting.value = true
  try {
    const res = await filesApi.extractPackage(
      extractForm.value.directory,
      extractForm.value.deleteAfterExtract
    )
    ElMessage.success(res.message || '提取成功')
    extractDialogVisible.value = false
    // 重置表单
    extractForm.value.deleteAfterExtract = false
    // 刷新列表
    await loadPackages()
  } catch (error) {
    ElMessage.error(error.detail || '提取失败')
  } finally {
    extracting.value = false
  }
}

const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

const formatTime = (timeStr) => {
  return formatDateTime(timeStr)
}

onMounted(() => {
  loadVersions()
  loadPackages()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.version-info {
  margin-bottom: 16px;
}

.running-badge {
  margin-left: 8px;
  font-size: 12px;
  color: var(--nginx-green);
}

.upload-section {
  margin-top: 16px;
}

.packages-section {
  margin-top: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}

.section-header .header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header .header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
}

.package-count {
  color: var(--text-secondary);
}

.filename-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-icon {
  color: var(--nginx-green);
  font-size: 18px;
}

.filename-text {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  width: 100%;
}
</style>
