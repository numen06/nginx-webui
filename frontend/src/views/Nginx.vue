<template>
  <div class="nginx-manager">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Nginx 版本列表</span>
          <div>
            <el-button type="primary" @click="downloadDialogVisible = true">
              在线下载源码包
            </el-button>
            <el-button type="cyan" @click="uploadDialogVisible = true">
              上传源码包
            </el-button>
            <el-button type="info" text @click="loadVersions">刷新</el-button>
            <el-tooltip content="强制释放 80 端口" placement="bottom">
              <el-button
                circle
                type="danger"
                size="small"
                class="force-release-btn"
                @click="forceReleaseHttpPort"
              >
                <span class="force-release-icon">⚡</span>
              </el-button>
            </el-tooltip>
          </div>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col
          v-for="row in versions"
          :key="row.version"
          :span="12"
        >
          <el-card class="version-card" shadow="hover">
            <template #header>
              <div class="version-card-header">
                <div class="version-title">
                  <span class="version-name">{{ row.version }}</span>
                  <div class="version-tags">
                    <el-tag
                      v-if="buildingVersions.includes(row.version)"
                      type="warning"
                      size="small"
                    >
                      处理中
                    </el-tag>
                    <template v-else>
                      <el-tag
                        v-if="row.compiled"
                        :type="row.running ? 'success' : 'info'"
                        size="small"
                      >
                        {{ row.running ? '运行中' : '已编译' }}
                      </el-tag>
                      <el-tag
                        v-else-if="row.has_source"
                        type="warning"
                        size="small"
                      >
                        未编译
                      </el-tag>
                      <el-tag
                        v-else
                        type="danger"
                        size="small"
                      >
                        未准备
                      </el-tag>
                    </template>
                  </div>
                </div>
                <div class="version-sub">
                  <span>PID：{{ row.pid || '-' }}</span>
                </div>
              </div>
            </template>

            <div class="version-body">
              <div class="install-path" :title="row.install_path">
                安装路径：{{ row.install_path }}
              </div>
            </div>

            <div class="version-actions">
              <el-button
                size="small"
                type="purple"
                :disabled="buildingVersions.includes(row.version) || row.compiled || !row.has_source"
                @click="compileVersion(row.version)"
              >
                编译
              </el-button>
              <el-button
                size="small"
                type="success"
                :disabled="row.running || buildingVersions.includes(row.version) || !row.compiled"
                @click="startVersion(row.version)"
              >
                启动
              </el-button>
              <el-button
                size="small"
                type="warning"
                :disabled="!row.running || buildingVersions.includes(row.version)"
                @click="stopVersion(row.version)"
              >
                停止
              </el-button>
              <el-button
                size="small"
                type="orange"
                :disabled="!row.running || buildingVersions.includes(row.version)"
                @click="forceStopVersion(row.version)"
              >
                强制停止
              </el-button>
              <el-button
                size="small"
                type="danger"
                :disabled="row.running || buildingVersions.includes(row.version)"
                @click="deleteVersion(row.version)"
              >
                删除
              </el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <!-- 在线下载并编译 弹窗 -->
    <el-dialog
      v-model="downloadDialogVisible"
      title="在线下载 Nginx 源码包"
      width="600px"
      :close-on-click-modal="false"
      @close="resetDownloadForm"
    >
      <el-form :model="downloadForm" label-width="100px">
        <el-form-item label="版本号">
          <el-select
            v-model="downloadForm.version"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入版本号，例如：1.28.0"
            style="width: 100%"
            @change="handleVersionChange"
          >
            <el-option
              v-for="item in builtinVersions"
              :key="item"
              :label="item"
              :value="item"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="下载地址">
          <el-input
            v-model="downloadForm.url"
            :placeholder="getDefaultUrl()"
            @blur="handleUrlBlur"
            clearable
            type="textarea"
            :rows="2"
            style="width: 100%"
          />
          <div style="margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary)">
            默认地址: {{ getDefaultUrl() }}
          </div>
          <div v-if="isUrlCheckResultValid(urlCheckResult)" style="margin-top: 8px; font-size: 12px">
            <el-alert
              v-if="urlCheckResult && urlCheckResult.accessible === true"
              type="success"
              :closable="false"
              show-icon
            >
              <template #default>
                <span>地址可访问</span>
                <span v-if="urlCheckResult && typeof urlCheckResult.content_length === 'number'" style="margin-left: 8px">
                  (大小: {{ formatFileSize(urlCheckResult.content_length) }})
                </span>
              </template>
            </el-alert>
            <el-alert
              v-else
              type="error"
              :closable="false"
              show-icon
            >
              <template #default>
                <span>地址不可访问: {{ getUrlCheckErrorMessage(urlCheckResult) }}</span>
              </template>
            </el-alert>
          </div>
        </el-form-item>
        <el-form-item v-if="downloadProgress.status === 'downloading'" label="下载进度">
          <el-progress
            :percentage="downloadProgress.percentage >= 0 ? downloadProgress.percentage : undefined"
            :status="downloadProgress.percentage >= 0 ? undefined : 'active'"
            :stroke-width="20"
          >
            <template #default="{ percentage }">
              <span v-if="percentage >= 0">{{ percentage }}%</span>
              <span v-else>下载中...</span>
            </template>
          </el-progress>
          <div style="margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary)">
            已下载: {{ formatFileSize(downloadProgress.downloaded) }}
            <span v-if="downloadProgress.total">
              / {{ formatFileSize(downloadProgress.total) }}
            </span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="downloadDialogVisible = false" :disabled="downloadLoading">
            取消
          </el-button>
          <el-button
            type="info"
            :loading="checkingUrl"
            :disabled="downloadLoading"
            @click="checkUrl"
          >
            检查地址
          </el-button>
          <el-button
            type="primary"
            :loading="downloadLoading"
            :disabled="urlCheckResult && typeof urlCheckResult === 'object' && urlCheckResult.accessible === false"
            @click="handleDownload"
          >
            下载源码包
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 上传源码包并编译 弹窗 -->
    <el-dialog
      v-model="uploadDialogVisible"
      title="上传 Nginx 源码包"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form label-width="100px">
        <el-form-item label="源码包">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :before-remove="() => !uploading"
          >
            <el-button type="primary">选择文件</el-button>
            <template #tip>
              <div class="el-upload__tip">
                仅支持 .tar.gz / .tgz 的 nginx 源码包，示例：nginx-1.28.0.tar.gz
              </div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="版本号">
          <el-input
            v-model="uploadVersion"
            placeholder="可留空，将从文件名 nginx-&lt;version&gt;.tar.gz 中推断"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="uploadDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="uploading"
            :disabled="!selectedFile"
            @click="handleUpload"
          >
            上传并编译
          </el-button>
        </span>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { nginxApi } from '../api/nginx'

const versions = ref([])
// 常用 Nginx 版本列表，用于下拉选择；也可以手动输入任意版本号
const builtinVersions = [
  '1.28.0', // mainline
  '1.26.2',
  '1.24.0',
  '1.22.1'
]
const downloadForm = ref({
  version: '',
  url: ''
})
const downloadLoading = ref(false)
const downloadDialogVisible = ref(false)
const checkingUrl = ref(false)
const urlCheckResult = ref(null)
const downloadProgress = ref({
  status: 'not_started',
  downloaded: 0,
  total: null,
  percentage: 0,
  error: null
})
let progressInterval = null

// 正在下载/编译的版本列表（前端感知的“进行中”状态）
const buildingVersions = ref([])

const setBuilding = (version, building) => {
  if (!version) return
  const idx = buildingVersions.value.indexOf(version)
  if (building && idx === -1) {
    buildingVersions.value.push(version)
  } else if (!building && idx !== -1) {
    buildingVersions.value.splice(idx, 1)
  }
}

const uploadRef = ref(null)
const selectedFile = ref(null)
const uploadVersion = ref('')
const uploading = ref(false)
const uploadDialogVisible = ref(false)

const loadVersions = async () => {
  try {
    const data = await nginxApi.listVersions()
    versions.value = data || []
  } catch (error) {
    ElMessage.error(error.detail || '获取版本列表失败')
  }
}

const getDefaultUrl = () => {
  if (downloadForm.value.version) {
    return `https://nginx.org/download/nginx-${downloadForm.value.version}.tar.gz`
  }
  return 'https://nginx.org/download/nginx-<version>.tar.gz'
}

const handleVersionChange = () => {
  // 当版本改变时，自动填充默认下载地址
  if (downloadForm.value.version) {
    const defaultUrl = getDefaultUrl()
    // 如果当前 URL 为空或者是默认地址格式，则自动填充
    if (!downloadForm.value.url || downloadForm.value.url.includes('nginx.org/download/nginx-')) {
      downloadForm.value.url = defaultUrl
    }
    // 重置检查结果
    urlCheckResult.value = null
  }
}

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

const isUrlCheckResultValid = (result) => {
  return result && typeof result === 'object' && !Array.isArray(result) && result !== null
}

const getUrlCheckErrorMessage = (result) => {
  try {
    if (!result || typeof result !== 'object' || Array.isArray(result)) {
      return '未知错误'
    }
    
    // 安全地访问 error 属性
    if ('error' in result) {
      const errorValue = result.error
      if (errorValue === null || errorValue === undefined) {
        return '未知错误'
      }
      if (typeof errorValue === 'string') {
        return errorValue
      }
      // 如果不是字符串，尝试转换
      try {
        return String(errorValue)
      } catch (e) {
        return '未知错误'
      }
    }
    
    return '未知错误'
  } catch (e) {
    console.error('获取错误信息失败:', e)
    return '未知错误'
  }
}

const checkUrl = async () => {
  // 如果没有输入 URL，使用默认地址
  const url = downloadForm.value.url || getDefaultUrl()
  
  if (!url || url.includes('<version>')) {
    ElMessage.warning('请先输入版本号或下载地址')
    return
  }

  checkingUrl.value = true
  urlCheckResult.value = null // 先清空之前的结果
  
  try {
    const result = await nginxApi.checkDownloadUrl(url)
    console.log('URL 检查结果:', result, typeof result, 'isArray:', Array.isArray(result))
    
    // 处理各种可能的返回格式
    let processedResult = null
    
    try {
      // 如果是字符串，尝试解析
      if (typeof result === 'string') {
        try {
          processedResult = JSON.parse(result)
          // 确保解析后是对象
          if (!processedResult || typeof processedResult !== 'object' || Array.isArray(processedResult)) {
            processedResult = {
              accessible: false,
              error: result
            }
          }
        } catch (e) {
          processedResult = {
            accessible: false,
            error: result
          }
        }
      }
      // 如果是对象且不是数组
      else if (result && typeof result === 'object' && !Array.isArray(result) && result !== null) {
        processedResult = result
      }
      // 其他情况（null, undefined, 数组等）
      else {
        processedResult = {
          accessible: false,
          error: '返回数据格式错误'
        }
      }
    } catch (e) {
      console.error('处理返回结果时出错:', e)
      processedResult = {
        accessible: false,
        error: '处理返回结果失败'
      }
    }
    
    // 确保对象包含必要的属性，统一格式
    // 安全地获取属性值
    let accessible = false
    if (processedResult.accessible === true || processedResult.accessible === 'true' || processedResult.accessible === 1) {
      accessible = true
    }
    
    let errorMsg = null
    if (processedResult.error !== undefined && processedResult.error !== null) {
      if (typeof processedResult.error === 'string') {
        errorMsg = processedResult.error
      } else {
        errorMsg = String(processedResult.error)
      }
    }
    
    urlCheckResult.value = {
      accessible: accessible,
      content_length: (typeof processedResult.content_length === 'number') ? processedResult.content_length : null,
      status_code: (typeof processedResult.status_code === 'number') ? processedResult.status_code : null,
      error: errorMsg
    }
    
    if (urlCheckResult.value.accessible) {
      ElMessage.success('地址可访问')
    } else {
      const displayError = urlCheckResult.value.error || '未知错误'
      ElMessage.error(`地址不可访问: ${displayError}`)
    }
  } catch (error) {
    console.error('URL 检查出错:', error, typeof error, error?.constructor?.name)
    
    // 确保错误处理总是创建对象
    let errorMessage = '检查失败'
    
    try {
      // 处理各种错误格式
      if (error) {
        if (typeof error === 'string') {
          errorMessage = error
        } else if (typeof error === 'object' && error !== null) {
          // 检查是否是 axios 错误对象
          if (error.response) {
            const responseData = error.response.data
            if (typeof responseData === 'string') {
              errorMessage = responseData
            } else if (responseData && typeof responseData === 'object' && !Array.isArray(responseData)) {
              // 安全地访问对象属性
              errorMessage = responseData.detail || responseData.message || responseData.error || '请求失败'
            } else {
              errorMessage = error.response.statusText || `HTTP ${error.response.status}`
            }
          } else if (error.request) {
            errorMessage = '无法连接到服务器'
          } else {
            // 尝试安全地获取错误信息
            if ('detail' in error && typeof error.detail === 'string') {
              errorMessage = error.detail
            } else if ('message' in error && typeof error.message === 'string') {
              errorMessage = error.message
            } else if ('error' in error && typeof error.error === 'string') {
              errorMessage = error.error
            } else {
              errorMessage = error.toString ? error.toString() : '检查失败'
            }
          }
        }
      }
    } catch (e) {
      // 如果错误处理本身出错，使用简单的字符串
      console.error('错误处理失败:', e)
      errorMessage = '检查失败，请查看控制台'
    }
    
    // 确保创建有效的错误对象
    urlCheckResult.value = {
      accessible: false,
      content_length: null,
      status_code: null,
      error: String(errorMessage)
    }
    
    ElMessage.error(String(errorMessage))
  } finally {
    checkingUrl.value = false
  }
}

const handleUrlBlur = () => {
  // URL 失焦时自动检查（如果有版本号或 URL）
  if (downloadForm.value.version || downloadForm.value.url) {
    // 延迟检查，避免在用户正在输入时触发
    setTimeout(() => {
      if (downloadForm.value.version || downloadForm.value.url) {
        checkUrl()
      }
    }, 300)
  }
}

const startProgressPolling = (version) => {
  // 清除之前的定时器
  if (progressInterval) {
    clearInterval(progressInterval)
  }
  
  // 重置进度
  downloadProgress.value = {
    status: 'downloading',
    downloaded: 0,
    total: null,
    percentage: 0,
    error: null
  }
  
  // 开始轮询进度
  progressInterval = setInterval(async () => {
    try {
      const progress = await nginxApi.getDownloadProgress(version)
      downloadProgress.value = progress
      
      // 如果完成或出错，停止轮询
      if (progress.status === 'completed' || progress.status === 'error') {
        if (progressInterval) {
          clearInterval(progressInterval)
          progressInterval = null
        }
        
        if (progress.status === 'error') {
          ElMessage.error(`下载失败: ${progress.error || '未知错误'}`)
        }
      }
    } catch (error) {
      console.error('获取下载进度失败:', error)
    }
  }, 500) // 每500ms查询一次
}

const stopProgressPolling = () => {
  if (progressInterval) {
    clearInterval(progressInterval)
    progressInterval = null
  }
  downloadProgress.value = {
    status: 'not_started',
    downloaded: 0,
    total: null,
    percentage: 0,
    error: null
  }
}

const resetDownloadForm = () => {
  downloadForm.value = {
    version: '',
    url: ''
  }
  urlCheckResult.value = null
  stopProgressPolling()
  checkingUrl.value = false
}

const handleDownload = async () => {
  if (!downloadForm.value.version) {
    ElMessage.warning('请先输入版本号')
    return
  }
  
  // 如果 URL 可访问性检查失败，阻止下载
  if (isUrlCheckResultValid(urlCheckResult.value) && urlCheckResult.value.accessible === false) {
    ElMessage.warning('下载地址不可访问，请检查后重试')
    return
  }
  
  const targetVersion = downloadForm.value.version
  // 如果没有输入 URL，使用默认地址
  const downloadUrl = downloadForm.value.url || getDefaultUrl()
  
  // 确保 URL 有效
  if (!downloadUrl || downloadUrl.includes('<version>')) {
    ElMessage.warning('下载地址无效，请检查版本号')
    return
  }
  
  downloadLoading.value = true
  setBuilding(targetVersion, true)
  
  // 开始进度轮询
  startProgressPolling(targetVersion)
  
  try {
    await nginxApi.downloadAndBuild({
      version: targetVersion,
      url: downloadUrl
    })
    
    // 等待一下，确保进度更新到100%
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    ElMessage.success('源码包下载成功')
    await loadVersions()
    downloadDialogVisible.value = false
    resetDownloadForm()
  } catch (error) {
    // 有些情况下后端实际上已经在后台继续下载，但前端因为超时收到了错误
    // 这里在报错前先刷新一次列表，如果目标版本已经出现，则提示"可能已完成"
    await loadVersions()
    const exists = versions.value?.some((v) => v.version === targetVersion && v.has_source)
    if (exists) {
      ElMessage.success('下载任务可能已在后台完成，请查看版本列表')
      downloadDialogVisible.value = false
      resetDownloadForm()
    } else {
      ElMessage.error(error.detail || '下载失败')
    }
  } finally {
    downloadLoading.value = false
    setBuilding(targetVersion, false)
    stopProgressPolling()
  }
}

const handleFileChange = (file) => {
  selectedFile.value = file.raw
}

const handleUpload = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择源码包文件')
    return
  }

  const formData = new FormData()
  formData.append('file', selectedFile.value)
  if (uploadVersion.value) {
    formData.append('version', uploadVersion.value)
  }

  uploading.value = true
  try {
    await nginxApi.uploadAndBuild(formData)
    ElMessage.success('上传并编译任务完成')
    await loadVersions()
    // 重置选择
    if (uploadRef.value) {
      uploadRef.value.clearFiles()
    }
    selectedFile.value = null
    uploadDialogVisible.value = false
  } catch (error) {
    ElMessage.error(error.detail || '上传编译失败')
  } finally {
    uploading.value = false
  }
}

const startVersion = async (version) => {
  try {
    await nginxApi.startVersion(version)
    ElMessage.success(`已启动 Nginx ${version}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '启动失败')
  }
}

const stopVersion = async (version) => {
  try {
    await nginxApi.stopVersion(version)
    ElMessage.success(`已停止 Nginx ${version}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '停止失败')
  }
}

const forceStopVersion = async (version) => {
  try {
    await nginxApi.forceStopVersion(version)
    ElMessage.success(`已强制停止 Nginx ${version}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '强制停止失败')
  }
}

const compileVersion = async (version) => {
  setBuilding(version, true)
  try {
    await nginxApi.compileVersion(version)
    ElMessage.success(`已编译 Nginx ${version}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '编译失败')
  } finally {
    setBuilding(version, false)
  }
}

const forceReleaseHttpPort = async () => {
  try {
    await nginxApi.forceReleaseHttpPort(80)
    ElMessage.success('已尝试强制释放 80 端口')
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '强制释放 80 端口失败')
  }
}

const deleteVersion = async (version) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除 Nginx 版本 ${version} 吗？此操作不可恢复，仅在该版本已停止时允许删除。`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    // 用户取消
    return
  }

  try {
    await nginxApi.deleteVersion(version)
    ElMessage.success(`已删除 Nginx ${version}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '删除失败')
  }
}

onMounted(() => {
  loadVersions()
})

// 组件卸载时清理定时器
onUnmounted(() => {
  stopProgressPolling()
})
</script>

<style scoped>
.nginx-manager {
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.version-card {
  margin-bottom: 16px;
}

.version-card-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.version-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.version-name {
  font-weight: 600;
  font-size: 14px;
}

.version-tags {
  display: flex;
  gap: 4px;
}

.version-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.version-body {
  margin-bottom: 12px;
  font-size: 13px;
}

.install-path {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.version-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.force-release-icon {
  font-size: 14px;
}

.force-release-btn {
  margin-left: 8px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  width: 100%;
}
</style>


