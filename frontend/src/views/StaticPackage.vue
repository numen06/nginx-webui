<template>
  <div class="static-package-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>静态资源包管理</span>
        </div>
      </template>

      <div class="version-info" v-if="selectedDirectory">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="当前 Nginx 目录">
            <el-text type="info" size="small">{{ selectedDirectory || '-' }}</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="当前 Nginx 版本">
            <template v-if="formatVersionLabel(currentVersionInfo)">
              <el-tag type="info" size="small">
                {{ formatVersionLabel(currentVersionInfo) }}
              </el-tag>
            </template>
            <span v-else style="color: var(--text-secondary)">未知</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="currentVersionInfo?.running" label="运行状态">
            <el-tag type="success" size="small">运行中</el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>


      <!-- 已上传资源包列表 -->
      <div class="packages-section">
        <div class="section-header">
          <div class="header-left">
            <h3>资源包列表</h3>
            <el-text type="info" size="small" class="package-count">
              共 {{ packages.length }} 个资源包
            </el-text>
          </div>
          <div class="header-right">
            <el-button
              type="info"
              :icon="Refresh"
              @click="loadPackages"
              :loading="loadingPackages"
            >
              刷新
            </el-button>
            <el-button
              type="warning"
              :icon="Download"
              @click="extractDialogVisible = true"
            >
              提取资源包
            </el-button>
            <el-button
              type="cyan"
              :icon="Upload"
              @click="uploadDialogVisible = true"
            >
              上传资源包
            </el-button>
          </div>
        </div>
        <el-table
          :data="packages"
          v-loading="loadingPackages"
          style="width: 100%"
          empty-text="暂无资源包，请先上传"
          stripe
        >
          <el-table-column label="文件名" min-width="250">
            <template #default="{ row }">
              <div class="filename-cell">
                <el-icon class="file-icon"><Document /></el-icon>
                <el-text class="filename-text" :title="row.filename">
                  {{ row.filename }}
                </el-text>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="120" align="right">
            <template #default="{ row }">
              <el-text type="info">{{ formatFileSize(row.size) }}</el-text>
            </template>
          </el-table-column>
          <el-table-column label="上传时间" width="180">
            <template #default="{ row }">
              <el-text type="info" size="small">
                {{ formatTime(row.uploaded_time) }}
              </el-text>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="380" fixed="right" align="center">
            <template #default="{ row }">
              <el-button
                type="success"
                size="small"
                :icon="Promotion"
                @click="handleDeployPackage(row.filename)"
                :loading="deploying === row.filename"
              >
                部署
              </el-button>
              <el-button
                type="primary"
                size="small"
                :icon="Download"
                @click="handleDownloadPackage(row.filename)"
                :loading="downloading === row.filename"
              >
                下载
              </el-button>
              <el-button
                type="danger"
                size="small"
                :icon="Delete"
                @click="handleDeletePackage(row.filename)"
                :loading="deleting === row.filename"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 上传对话框 -->
    <el-dialog
      v-model="uploadDialogVisible"
      title="上传静态资源包"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="uploadForm" label-width="140px">
        <el-form-item label="资源包文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :before-remove="() => !uploading"
            accept=".zip,.tar.gz,.tgz,.tar"
          >
            <el-button type="primary">
              <el-icon><FolderOpened /></el-icon>
              <span class="btn-label">选择文件</span>
            </el-button>
            <template #tip>
              <div class="el-upload__tip">
                支持 .zip、.tar.gz、.tgz、.tar 格式
              </div>
            </template>
          </el-upload>
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
            :disabled="!selectedFile"
            @click="handleUpload"
          >
            <el-icon><UploadFilled /></el-icon>
            <span class="btn-label">上传</span>
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 提取资源包对话框 -->
    <el-dialog
      v-model="extractDialogVisible"
      title="提取静态资源包"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="extractForm" label-width="140px">
        <el-form-item label="选择 Nginx 目录/版本">
          <el-select
            v-model="extractForm.directory"
            placeholder="选择 Nginx 目录/版本"
            style="width: 100%"
          >
            <el-option
              v-for="version in versions"
              :key="version.directory"
              :label="formatOptionLabel(version)"
              :value="version.directory"
            />
          </el-select>
        </el-form-item>
        <el-alert
          title="说明"
          type="info"
          :closable="false"
          style="margin-bottom: 15px"
        >
          <template #default>
            将扫描静态文件夹（html目录）中的压缩包文件（.zip、.tar.gz、.tgz、.tar），
            并将它们提取到资源包存储目录。
          </template>
        </el-alert>
        <el-form-item label="提取选项">
          <el-switch
            v-model="extractForm.deleteAfterExtract"
            active-text="提取后删除静态文件夹中的资源包"
            inactive-text="保留源文件"
          />
        </el-form-item>
        <el-alert
          v-if="extractForm.deleteAfterExtract"
          title="警告"
          type="warning"
          :closable="false"
          style="margin-top: 10px"
        >
          <template #default>
            提取后将删除静态文件夹（html目录）中的资源包文件，此操作不可恢复！
          </template>
        </el-alert>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="extractDialogVisible = false">
            <el-icon><CloseBold /></el-icon>
            <span class="btn-label">取消</span>
          </el-button>
          <el-button
            type="warning"
            :loading="extracting"
            :disabled="!extractForm.directory"
            @click="handleExtractConfirm"
          >
            <el-icon><Download /></el-icon>
            <span class="btn-label">确认提取</span>
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 部署对话框 -->
    <el-dialog
      v-model="deployDialogVisible"
      title="部署静态资源包"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="deployForm" label-width="140px">
        <el-form-item label="资源包">
          <el-text>{{ deployForm.filename }}</el-text>
        </el-form-item>
        <el-form-item label="选择 Nginx 目录/版本">
          <el-select
            v-model="deployForm.directory"
            placeholder="选择 Nginx 目录/版本"
            style="width: 100%"
          >
            <el-option
              v-for="version in versions"
              :key="version.directory"
              :label="formatOptionLabel(version)"
              :value="version.directory"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="解压选项">
          <el-radio-group v-model="deployForm.extractToSubdir">
            <el-radio :label="false">直接解压到 html 根目录</el-radio>
            <el-radio :label="true">解压到子目录（使用包名）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="deployDialogVisible = false">
            <el-icon><CloseBold /></el-icon>
            <span class="btn-label">取消</span>
          </el-button>
          <el-button
            type="success"
            :loading="deploying"
            :disabled="!deployForm.directory"
            @click="handleDeployConfirm"
          >
            <el-icon><CircleCheck /></el-icon>
            <span class="btn-label">确认部署</span>
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Upload, Document, Promotion, Delete, FolderOpened, CloseBold, UploadFilled, CircleCheck, Download } from '@element-plus/icons-vue'
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

const handleDownloadPackage = async (filename) => {
  downloading.value = filename
  try {
    const blob = await filesApi.downloadPackage(filename)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch (error) {
    ElMessage.error(error.detail || '下载失败')
  } finally {
    downloading.value = null
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

.packages-section {
  margin-top: 30px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 15px;
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

.upload-section {
  margin-top: 20px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  width: 100%;
}
</style>

