<template>
  <div class="nginx-manager">
    <div v-if="pinnedVersion" class="pinned-card-wrapper">
      <el-card 
        class="version-card pinned-card" 
        :class="{ 'running-version': pinnedVersion.running }"
        shadow="hover"
      >
        <template #header>
          <div class="version-card-header">
            <div class="version-title">
              <div class="version-name">
                <span class="directory-text">目录：{{ pinnedVersion.directory }}</span>
                <span class="running-flag">（发布版）</span>
              </div>
              <div class="version-tags">
                <el-tag
                  v-if="buildingVersions.includes(pinnedVersion.directory)"
                  type="warning"
                  size="small"
                >
                  处理中
                </el-tag>
                <template v-else>
                  <el-tag
                    v-if="pinnedVersion.compiled"
                    :type="pinnedVersion.running ? 'success' : 'info'"
                    size="small"
                  >
                    {{ pinnedVersion.running ? '运行中' : '已编译' }}
                  </el-tag>
                  <el-tag
                    v-else-if="pinnedVersion.has_source"
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
              <span>版本：{{ formatVersionLabel(pinnedVersion) }}</span>
              <span>PID：{{ pinnedVersion.pid || '-' }}</span>
            </div>
          </div>
        </template>

        <div class="version-body">
          <div class="install-path" :title="pinnedVersion.install_path">
            安装路径：{{ pinnedVersion.install_path }}
          </div>
        </div>

        <div class="version-actions">
          <template v-if="pinnedVersion.directory !== 'last'">
            <el-tooltip class="action-tooltip" content="编译" placement="top">
              <el-button
                circle
                size="small"
                type="purple"
                class="action-icon-btn"
                :disabled="buildingVersions.includes(pinnedVersion.directory) || pinnedVersion.compiled || !pinnedVersion.has_source"
                @click="compileVersion(pinnedVersion.directory)"
              >
                <el-icon><Tools /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip class="action-tooltip" content="发布" placement="top">
              <el-button
                circle
                size="small"
                type="primary"
                class="action-icon-btn"
                :disabled="buildingVersions.includes(pinnedVersion.directory) || !pinnedVersion.compiled"
                @click="upgradeToProduction(pinnedVersion.directory)"
              >
                <el-icon><Promotion /></el-icon>
              </el-button>
            </el-tooltip>
          </template>
          <el-tooltip class="action-tooltip" content="启动" placement="top">
            <el-button
              circle
              size="small"
              type="success"
              class="action-icon-btn"
              :disabled="pinnedVersion.running || buildingVersions.includes(pinnedVersion.directory) || !pinnedVersion.compiled"
              @click="startVersion(pinnedVersion.directory)"
            >
              <el-icon><VideoPlay /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip class="action-tooltip" content="停止" placement="top">
            <el-button
              circle
              size="small"
              type="warning"
              class="action-icon-btn"
              :disabled="!pinnedVersion.running || buildingVersions.includes(pinnedVersion.directory)"
              @click="stopVersion(pinnedVersion.directory)"
            >
              <el-icon><VideoPause /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip class="action-tooltip" content="强制停止" placement="top">
            <el-button
              circle
              size="small"
              type="orange"
              class="action-icon-btn"
              :disabled="!pinnedVersion.running || buildingVersions.includes(pinnedVersion.directory)"
              @click="forceStopVersion(pinnedVersion.directory)"
            >
              <el-icon><Lightning /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip class="action-tooltip" content="删除" placement="top">
            <el-button
              circle
              size="small"
              type="danger"
              class="action-icon-btn"
              :disabled="pinnedVersion.running || buildingVersions.includes(pinnedVersion.directory)"
              @click="deleteVersion(pinnedVersion.directory)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </el-card>
    </div>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>Nginx 版本列表</span>
          <div>
            <el-button type="primary" @click="downloadDialogVisible = true">
              <el-icon><Download /></el-icon>
              <span class="btn-label">在线下载源码包</span>
            </el-button>
            <el-button type="cyan" @click="uploadDialogVisible = true">
              <el-icon><UploadFilled /></el-icon>
              <span class="btn-label">上传源码包</span>
            </el-button>
            <el-button type="info" text @click="loadVersions">
              <el-icon><RefreshRight /></el-icon>
              <span class="btn-label">刷新</span>
            </el-button>
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
          v-for="row in sortedVersions"
          :key="row.directory"
          :span="12"
        >
          <el-card 
            class="version-card" 
            :class="{ 'running-version': row.running }"
            shadow="hover"
          >
            <template #header>
              <div class="version-card-header">
                <div class="version-title">
                  <div class="version-name">
                    <span class="directory-text">目录：{{ row.directory }}</span>
                  </div>
                  <div class="version-tags">
                    <el-tag
                      v-if="buildingVersions.includes(row.directory)"
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
                  <span>版本：{{ formatVersionLabel(row) }}</span>
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
              <el-tooltip class="action-tooltip" content="编译" placement="top">
                <el-button
                  circle
                  size="small"
                  type="purple"
                  class="action-icon-btn"
                  :disabled="buildingVersions.includes(row.directory) || row.compiled || !row.has_source"
                  @click="compileVersion(row.directory)"
                >
                  <el-icon><Tools /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip class="action-tooltip" content="发布" placement="top">
                <el-button
                  circle
                  size="small"
                  type="primary"
                  class="action-icon-btn"
                  :disabled="buildingVersions.includes(row.directory) || !row.compiled"
                  @click="upgradeToProduction(row.directory)"
                >
                  <el-icon><Promotion /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip class="action-tooltip" content="启动" placement="top">
                <el-button
                  circle
                  size="small"
                  type="success"
                  class="action-icon-btn"
                  :disabled="row.running || buildingVersions.includes(row.directory) || !row.compiled"
                  @click="startVersion(row.directory)"
                >
                  <el-icon><VideoPlay /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip class="action-tooltip" content="停止" placement="top">
                <el-button
                  circle
                  size="small"
                  type="warning"
                  class="action-icon-btn"
                  :disabled="!row.running || buildingVersions.includes(row.directory)"
                  @click="stopVersion(row.directory)"
                >
                  <el-icon><VideoPause /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip class="action-tooltip" content="强制停止" placement="top">
                <el-button
                  circle
                  size="small"
                  type="orange"
                  class="action-icon-btn"
                  :disabled="!row.running || buildingVersions.includes(row.directory)"
                  @click="forceStopVersion(row.directory)"
                >
                  <el-icon><Lightning /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip class="action-tooltip" content="删除" placement="top">
                <el-button
                  circle
                  size="small"
                  type="danger"
                  class="action-icon-btn"
                  :disabled="row.running || buildingVersions.includes(row.directory)"
                  @click="deleteVersion(row.directory)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </el-tooltip>
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
          <div style="display: flex; gap: 8px; align-items: center; width: 100%">
            <el-select
              v-model="downloadForm.version"
              filterable
              allow-create
              default-first-option
              placeholder="选择或输入版本号，例如：1.28.0"
              style="flex: 1"
              @change="handleVersionChange"
            >
              <el-option-group label="最新版本（来自 nginx.org）">
                <el-option
                  v-for="item in builtinVersions"
                  :key="item"
                  :label="item"
                  :value="item"
                />
              </el-option-group>
            </el-select>
            <el-button
              type="info"
              :loading="loadingLatestVersions"
              @click="loadLatestVersions"
              size="small"
            >
              <el-icon><RefreshRight /></el-icon>
              <span class="btn-label">获取最新</span>
            </el-button>
          </div>
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
            <el-icon><CloseBold /></el-icon>
            <span class="btn-label">取消</span>
          </el-button>
          <el-button
            type="info"
            :loading="checkingUrl"
            :disabled="downloadLoading"
            @click="checkUrl"
          >
            <el-icon><Link /></el-icon>
            <span class="btn-label">检查地址</span>
          </el-button>
          <el-button
            type="primary"
            :loading="downloadLoading"
            :disabled="urlCheckResult && typeof urlCheckResult === 'object' && urlCheckResult.accessible === false"
            @click="handleDownload"
          >
            <el-icon><Download /></el-icon>
            <span class="btn-label">下载源码包</span>
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
            <el-button type="primary">
              <el-icon><FolderOpened /></el-icon>
              <span class="btn-label">选择文件</span>
            </el-button>
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
            <span class="btn-label">上传并编译</span>
          </el-button>
        </span>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { nginxApi } from '../api/nginx'
import {
  Tools,
  Promotion,
  VideoPlay,
  VideoPause,
  Lightning,
  Delete,
  Download,
  UploadFilled,
  RefreshRight,
  CloseBold,
  Link,
  FolderOpened
} from '@element-plus/icons-vue'

const versions = ref([])
const pinnedVersion = computed(() => versions.value.find((item) => item.directory === 'last'))
const sortedVersions = computed(() => {
  if (!versions.value || versions.value.length === 0) {
    return []
  }
  if (!pinnedVersion.value) {
    return versions.value
  }
  return [
    ...versions.value.filter((item) => item.directory !== 'last')
  ]
})
// 常用 Nginx 版本列表，用于下拉选择；也可以手动输入任意版本号
const builtinVersions = ref([
  '1.28.0', // mainline
  '1.26.2',
  '1.24.0',
  '1.22.1'
])
const loadingLatestVersions = ref(false)
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

const formatVersionLabel = (info) => {
  if (!info || typeof info !== 'object') {
    return '未知'
  }
  return info.version || '未知'
}

const getDisplayLabelByDirectory = (directory) => {
  if (!directory) return ''
  const target = versions.value.find((item) => item.directory === directory)
  if (target && target.version) {
    if (target.version !== target.directory) {
      return `${target.version}（目录 ${target.directory}）`
    }
    return target.version
  }
  return target?.directory || directory
}

const setBuilding = (directory, building) => {
  if (!directory) return
  const idx = buildingVersions.value.indexOf(directory)
  if (building && idx === -1) {
    buildingVersions.value.push(directory)
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

const loadLatestVersions = async () => {
  loadingLatestVersions.value = true
  try {
    const response = await nginxApi.getLatestVersions(5)
    if (response.success && response.versions && response.versions.length > 0) {
      builtinVersions.value = response.versions
      ElMessage.success(`已获取 ${response.versions.length} 个最新版本`)
    } else {
      ElMessage.warning(response.message || '获取最新版本失败')
    }
  } catch (error) {
    ElMessage.error(error.detail || error.message || '获取最新版本列表失败')
  } finally {
    loadingLatestVersions.value = false
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

const startProgressPolling = (version, onComplete) => {
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
        
        // 调用完成回调
        if (onComplete) {
          onComplete(progress.status === 'completed')
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
  
  try {
    // 启动下载任务（后端会立即返回，下载在后台进行）
    await nginxApi.downloadAndBuild({
      version: targetVersion,
      url: downloadUrl
    })
    
    // 开始进度轮询，等待下载完成
    let downloadCompleted = false
    let downloadError = null
    
    await new Promise((resolve) => {
      startProgressPolling(targetVersion, (success) => {
        downloadCompleted = success
        resolve()
      })
      
      // 设置超时（最多等待1小时）
      setTimeout(() => {
        if (progressInterval) {
          clearInterval(progressInterval)
          progressInterval = null
        }
        downloadError = '下载超时，请稍后刷新版本列表查看'
        resolve()
      }, 3600000) // 1小时超时
    })
    
    // 下载完成后的处理
    if (downloadCompleted) {
      ElMessage.success('源码包下载成功')
      await loadVersions()
      downloadDialogVisible.value = false
      resetDownloadForm()
    } else if (downloadError) {
      ElMessage.warning(downloadError)
      await loadVersions()
    } else {
      // 下载失败的情况已在进度轮询中处理
      await loadVersions()
    }
  } catch (error) {
    // 启动下载任务失败
    stopProgressPolling()
    ElMessage.error(error.detail || error.message || '启动下载任务失败')
    await loadVersions()
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

const startVersion = async (directory) => {
  try {
    await nginxApi.startVersion(directory)
    ElMessage.success(`已启动 Nginx ${getDisplayLabelByDirectory(directory)}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '启动失败')
  }
}

const stopVersion = async (directory) => {
  try {
    await nginxApi.stopVersion(directory)
    ElMessage.success(`已停止 Nginx ${getDisplayLabelByDirectory(directory)}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '停止失败')
  }
}

const forceStopVersion = async (directory) => {
  try {
    await nginxApi.forceStopVersion(directory)
    ElMessage.success(`已强制停止 Nginx ${getDisplayLabelByDirectory(directory)}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '强制停止失败')
  }
}

const compileVersion = async (directory) => {
  setBuilding(directory, true)
  try {
    await nginxApi.compileVersion(directory)
    ElMessage.success(`已编译 Nginx ${getDisplayLabelByDirectory(directory)}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '编译失败')
  } finally {
    setBuilding(directory, false)
  }
}

const upgradeToProduction = async (directory) => {
  const target = versions.value.find((item) => item.directory === directory)
  const binaryVersion = target ? formatVersionLabel(target) : ''
  const directoryDesc =
    binaryVersion && binaryVersion !== directory
      ? `目录 ${directory}（版本 ${binaryVersion}）`
      : `目录 ${directory}`
  try {
    await ElMessageBox.confirm(
      `确认将 ${directoryDesc} 发布到运行目录（last）？发布将覆盖当前运行版本的核心文件，但会保留 html/conf/logs 中的自定义内容。发布后需手动重启 Nginx 生效。`,
      '发布确认',
      {
        confirmButtonText: '发布',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }

  setBuilding(directory, true)
  try {
    await nginxApi.upgradeToProduction(directory)
    ElMessage.success(`已将 ${getDisplayLabelByDirectory(directory)} 发布到发布版（last）`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '发布失败')
  } finally {
    setBuilding(directory, false)
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

const deleteVersion = async (directory) => {
  const target = versions.value.find((item) => item.directory === directory)
  const binaryVersion = target ? formatVersionLabel(target) : ''
  const directoryDesc =
    binaryVersion && binaryVersion !== directory
      ? `目录 ${directory}（版本 ${binaryVersion}）`
      : `目录 ${directory}`
  try {
    await ElMessageBox.confirm(
      `确定要删除 ${directoryDesc} 吗？此操作不可恢复，仅在该版本已停止时允许删除。`,
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
    await nginxApi.deleteVersion(directory)
    ElMessage.success(`已删除 Nginx ${getDisplayLabelByDirectory(directory)}`)
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '删除失败')
  }
}

// 监听下载对话框打开，自动加载最新版本
watch(downloadDialogVisible, (visible) => {
  if (visible) {
    loadLatestVersions()
  }
})

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

.pinned-card-wrapper {
  margin-bottom: 16px;
}

.pinned-card .version-name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.version-tags {
  display: flex;
  gap: 4px;
}

.version-sub {
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
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

.action-tooltip {
  display: inline-flex;
}

.action-icon-btn {
  width: 32px;
  height: 32px;
  padding: 0;
}

.action-icon-btn .el-icon {
  font-size: 16px;
}

.directory-text {
  font-weight: 600;
}

.running-flag {
  color: var(--el-color-primary);
}

.force-release-icon {
  font-size: 14px;
}

.force-release-btn {
  margin-left: 8px;
}

.running-version {
  border: 2px solid var(--el-color-success);
  box-shadow: 0 2px 12px 0 rgba(103, 194, 58, 0.3);
  background: linear-gradient(to bottom, rgba(103, 194, 58, 0.05), transparent);
}

.running-version:hover {
  box-shadow: 0 4px 16px 0 rgba(103, 194, 58, 0.4);
  transform: translateY(-2px);
  transition: all 0.3s ease;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  width: 100%;
}
</style>


