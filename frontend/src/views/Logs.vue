<template>
  <div class="logs-page">
    <el-tabs v-model="activeTab" class="logs-tabs" stretch>
      <el-tab-pane label="访问日志" name="access">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>访问日志</span>
              <div class="header-actions">
                <el-button 
                  type="warning"
                  size="small" 
                  @click="handleRotateLogs"
                  :loading="rotating"
                  :icon="Switch"
                >
                  立即分片
                </el-button>
                <el-button 
                  :icon="Refresh" 
                  circle 
                  size="small" 
                  @click="loadLogs"
                  :loading="loading"
                />
              </div>
            </div>
          </template>
          <div class="log-info">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item v-if="accessLogInfo.install_path" label="当前 Nginx 目录">
                <el-text type="info" size="small">{{ accessLogInfo.install_path }}</el-text>
              </el-descriptions-item>
              <el-descriptions-item label="当前 Nginx 版本">
                <el-tooltip
                  v-if="accessLogInfo.nginx_version"
                  :content="accessLogInfo.nginx_version"
                  placement="top"
                >
                  <el-tag type="info" size="small" class="version-tag">
                    {{ formatShortVersion(accessLogInfo.nginx_version) }}
                  </el-tag>
                </el-tooltip>
                <span v-else class="text-muted">未知</span>
              </el-descriptions-item>
              <el-descriptions-item label="日志文件路径" :span="2">
                <div v-if="currentAccessRotateFile" class="rotate-file-indicator">
                  <el-tag type="warning" size="small" style="margin-right: 8px;">
                    分片文件
                  </el-tag>
                  <el-text class="log-path" size="small">
                    {{ currentAccessRotateFile }}
                  </el-text>
                  <el-button
                    type="text"
                    size="small"
                    @click="selectAccessRotateFile({ filename: currentAccessRotateFile })"
                    style="margin-left: 8px; padding: 0 4px;"
                  >
                    返回当前日志
                  </el-button>
                </div>
                <el-text v-else-if="accessLogInfo.log_path" class="log-path" size="small">
                  {{ accessLogInfo.log_path }}
                </el-text>
                <span v-else class="text-muted">未知</span>
              </el-descriptions-item>
              <el-descriptions-item label="日志文件大小">
                <el-text v-if="accessLogInfo.log_size_bytes != null" type="info" size="small">
                  {{ formatFileSize(accessLogInfo.log_size_bytes) }}
                </el-text>
                <span v-else class="text-muted">未知</span>
              </el-descriptions-item>
              <el-descriptions-item v-if="accessLogInfo.nginx_version_detail" label="版本详情" :span="2">
                <el-text type="info" size="small">{{ accessLogInfo.nginx_version_detail }}</el-text>
              </el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="log-rotate-section" v-if="accessRotateFiles.length > 0">
            <div class="rotate-files-header">
              <span class="rotate-files-title">访问日志分片 ({{ accessRotateFiles.length }})</span>
            </div>
            <div class="rotate-files-list">
              <el-tag
                v-for="file in accessRotateFiles"
                :key="file.filename"
                size="small"
                :type="accessFilters.selectedRotateFile === file.filename ? 'warning' : 'info'"
                class="rotate-file-tag"
                :title="`${file.filename} - ${formatFileSize(file.size)}`"
                @click="selectAccessRotateFile(file)"
                closable
                @close="deleteAccessRotateFile(file)"
                style="cursor: pointer;"
              >
                {{ file.date }}
              </el-tag>
            </div>
          </div>
          <div class="log-filters">
            <el-form :inline="true" class="filter-form">
              <el-form-item label="关键词搜索">
                <el-input
                  v-model="accessFilters.keyword"
                  placeholder="输入关键词搜索日志"
                  clearable
                  style="width: 250px"
                  @clear="handleAccessSearch"
                  @keyup.enter="handleAccessSearch"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>
              </el-form-item>
              <el-form-item label="日期范围">
                <el-date-picker
                  v-model="accessFilters.dateRange"
                  type="datetimerange"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  format="YYYY-MM-DD HH:mm:ss"
                  value-format="YYYY-MM-DD HH:mm:ss"
                  @change="handleAccessSearch"
                />
              </el-form-item>
              <el-form-item label="快捷选择">
                <div class="quick-time-buttons">
                  <el-button size="small" @click="setAccessQuickTime(15)">15分钟</el-button>
                  <el-button size="small" @click="setAccessQuickTime(30)">30分钟</el-button>
                  <el-button size="small" @click="setAccessQuickTime(60)">1小时</el-button>
                  <el-button size="small" @click="setAccessQuickTime(60 * 3)">3小时</el-button>
                  <el-button size="small" @click="setAccessQuickTime(60 * 6)">6小时</el-button>
                  <el-button size="small" @click="setAccessQuickTime(60 * 12)">12小时</el-button>
                  <el-button size="small" @click="setAccessQuickTime(60 * 24)">1天</el-button>
                  <el-button size="small" @click="setAccessQuickTime(60 * 24 * 7)">7天</el-button>
                </div>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleAccessSearch">
                  <el-icon><Search /></el-icon>
                  <span class="btn-label">搜索</span>
                </el-button>
                <el-button type="info" @click="handleAccessReset">
                  <el-icon><RefreshRight /></el-icon>
                  <span class="btn-label">重置</span>
                </el-button>
              </el-form-item>
            </el-form>
          </div>
          <div v-loading="loading" class="log-content">
            <div v-if="!loading && (!accessLogs || accessLogs.length === 0)" class="empty-log">
              <el-empty description="暂无访问日志" />
            </div>
            <LogViewer
              v-else
              :logs="accessLogs"
              :keyword="accessFilters.keyword"
              :show-line-numbers="true"
              filename="access-log"
              ref="accessLogViewerRef"
            />
            <div
              v-if="accessHasMore && !loading && accessLogs && accessLogs.length > 0"
              class="load-more-wrapper"
            >
              <el-button size="small" type="info" @click="loadMoreAccess">
                加载更早的 100 行
              </el-button>
            </div>
          </div>
        </el-card>
      </el-tab-pane>
      <el-tab-pane label="错误日志" name="error">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>错误日志</span>
              <div class="header-actions">
                <el-button 
                  type="warning"
                  size="small" 
                  @click="handleRotateLogs"
                  :loading="rotating"
                  :icon="Switch"
                >
                  立即分片
                </el-button>
                <el-button 
                  :icon="Refresh" 
                  circle 
                  size="small" 
                  @click="loadLogs"
                  :loading="loading"
                />
              </div>
            </div>
          </template>
          <div class="log-info">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item v-if="errorLogInfo.install_path" label="当前 Nginx 目录">
                <el-text type="info" size="small">{{ errorLogInfo.install_path }}</el-text>
              </el-descriptions-item>
              <el-descriptions-item label="当前 Nginx 版本">
                <el-tooltip
                  v-if="errorLogInfo.nginx_version"
                  :content="errorLogInfo.nginx_version"
                  placement="top"
                >
                  <el-tag type="info" size="small" class="version-tag">
                    {{ formatShortVersion(errorLogInfo.nginx_version) }}
                  </el-tag>
                </el-tooltip>
                <span v-else class="text-muted">未知</span>
              </el-descriptions-item>
              <el-descriptions-item label="日志文件路径" :span="2">
                <div v-if="currentErrorRotateFile" class="rotate-file-indicator">
                  <el-tag type="warning" size="small" style="margin-right: 8px;">
                    分片文件
                  </el-tag>
                  <el-text class="log-path" size="small">
                    {{ currentErrorRotateFile }}
                  </el-text>
                  <el-button
                    type="text"
                    size="small"
                    @click="selectErrorRotateFile({ filename: currentErrorRotateFile })"
                    style="margin-left: 8px; padding: 0 4px;"
                  >
                    返回当前日志
                  </el-button>
                </div>
                <el-text v-else-if="errorLogInfo.log_path" class="log-path" size="small">
                  {{ errorLogInfo.log_path }}
                </el-text>
                <span v-else class="text-muted">未知</span>
              </el-descriptions-item>
              <el-descriptions-item label="日志文件大小">
                <el-text v-if="errorLogInfo.log_size_bytes != null" type="info" size="small">
                  {{ formatFileSize(errorLogInfo.log_size_bytes) }}
                </el-text>
                <span v-else class="text-muted">未知</span>
              </el-descriptions-item>
              <el-descriptions-item v-if="errorLogInfo.nginx_version_detail" label="版本详情" :span="2">
                <el-text type="info" size="small">{{ errorLogInfo.nginx_version_detail }}</el-text>
              </el-descriptions-item>
            </el-descriptions>
          </div>
          <div class="log-rotate-section" v-if="errorRotateFiles.length > 0">
            <div class="rotate-files-header">
              <span class="rotate-files-title">错误日志分片 ({{ errorRotateFiles.length }})</span>
            </div>
            <div class="rotate-files-list">
              <el-tag
                v-for="file in errorRotateFiles"
                :key="file.filename"
                size="small"
                :type="errorFilters.selectedRotateFile === file.filename ? 'warning' : 'info'"
                class="rotate-file-tag"
                :title="`${file.filename} - ${formatFileSize(file.size)}`"
                @click="selectErrorRotateFile(file)"
                closable
                @close="deleteErrorRotateFile(file)"
                style="cursor: pointer;"
              >
                {{ file.date }}
              </el-tag>
            </div>
          </div>
          <div class="log-filters">
            <el-form :inline="true" class="filter-form">
              <el-form-item label="关键词搜索">
                <el-input
                  v-model="errorFilters.keyword"
                  placeholder="输入关键词搜索日志"
                  clearable
                  style="width: 250px"
                  @clear="handleErrorSearch"
                  @keyup.enter="handleErrorSearch"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>
              </el-form-item>
              <el-form-item label="日期范围">
                <el-date-picker
                  v-model="errorFilters.dateRange"
                  type="datetimerange"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  format="YYYY-MM-DD HH:mm:ss"
                  value-format="YYYY-MM-DD HH:mm:ss"
                  @change="handleErrorSearch"
                />
              </el-form-item>
              <el-form-item label="快捷选择">
                <div class="quick-time-buttons">
                  <el-button size="small" @click="setErrorQuickTime(15)">15分钟</el-button>
                  <el-button size="small" @click="setErrorQuickTime(30)">30分钟</el-button>
                  <el-button size="small" @click="setErrorQuickTime(60)">1小时</el-button>
                  <el-button size="small" @click="setErrorQuickTime(60 * 3)">3小时</el-button>
                  <el-button size="small" @click="setErrorQuickTime(60 * 6)">6小时</el-button>
                  <el-button size="small" @click="setErrorQuickTime(60 * 12)">12小时</el-button>
                  <el-button size="small" @click="setErrorQuickTime(60 * 24)">1天</el-button>
                  <el-button size="small" @click="setErrorQuickTime(60 * 24 * 7)">7天</el-button>
                </div>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleErrorSearch">
                  <el-icon><Search /></el-icon>
                  <span class="btn-label">搜索</span>
                </el-button>
                <el-button type="info" @click="handleErrorReset">
                  <el-icon><RefreshRight /></el-icon>
                  <span class="btn-label">重置</span>
                </el-button>
              </el-form-item>
            </el-form>
          </div>
          <div v-loading="loading" class="log-content">
            <div v-if="!loading && (!errorLogs || errorLogs.length === 0)" class="empty-log">
              <el-empty description="暂无错误日志" />
            </div>
            <LogViewer
              v-else
              :logs="errorLogs"
              :keyword="errorFilters.keyword"
              :show-line-numbers="true"
              filename="error-log"
              ref="errorLogViewerRef"
            />
            <div
              v-if="errorHasMore && !loading && errorLogs && errorLogs.length > 0"
              class="load-more-wrapper"
            >
              <el-button size="small" type="info" @click="loadMoreError">
                加载更早的 100 行
              </el-button>
            </div>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { logsApi } from '../api/logs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, RefreshRight, Switch } from '@element-plus/icons-vue'
import LogViewer from '../components/LogViewer.vue'
import { formatDateTime } from '../utils/date'

const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 B'
  if (bytes == null || Number.isNaN(bytes)) return '-'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const value = bytes / Math.pow(k, i)
  return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${sizes[i]}`
}

const activeTab = ref('access')
const loading = ref(false)
const accessLogs = ref([])
const errorLogs = ref([])
const accessLogInfo = ref({
  nginx_version: null,
  nginx_version_detail: null,
  log_path: null,
  log_size_bytes: null,
  active_version: null,
  install_path: null,
  binary: null
})
const errorLogInfo = ref({
  nginx_version: null,
  nginx_version_detail: null,
  log_path: null,
  log_size_bytes: null,
  active_version: null,
  install_path: null,
  binary: null
})
const accessFilters = ref({
  keyword: '',
  dateRange: null,
  selectedRotateFile: null
})
const errorFilters = ref({
  keyword: '',
  dateRange: null,
  selectedRotateFile: null
})
const currentAccessRotateFile = ref(null)
const currentErrorRotateFile = ref(null)
const accessLogViewerRef = ref(null)
const errorLogViewerRef = ref(null)
const MAX_VERSION_LABEL_LENGTH = 20

// 日志分页相关（仅查看最近部分日志，支持逐步向上加载）
const ACCESS_PAGE_SIZE = 100
const ERROR_PAGE_SIZE = 100
const accessPage = ref(1)
const errorPage = ref(1)
const accessHasMore = ref(false)
const errorHasMore = ref(false)
const rotating = ref(false)
const accessRotateFiles = ref([])
const errorRotateFiles = ref([])

const formatShortVersion = (text) => {
  if (!text) return ''
  return text.length > MAX_VERSION_LABEL_LENGTH
    ? `${text.slice(0, MAX_VERSION_LABEL_LENGTH)}…`
    : text
}

const loadLogs = async () => {
  loading.value = true
  try {
    if (activeTab.value === 'access') {
      // 重置为第一页，默认查看最近的 1000 行
      accessPage.value = 1
      const keyword = accessFilters.value.keyword || null
      const startDate = accessFilters.value.dateRange?.[0] || null
      const endDate = accessFilters.value.dateRange?.[1] || null
      const rotateFile = accessFilters.value.selectedRotateFile || null
      const response = await logsApi.getAccessLogs(accessPage.value, ACCESS_PAGE_SIZE, keyword, startDate, endDate, rotateFile)
      console.log('访问日志响应:', response)
      if (response && response.success !== false) {
        accessLogs.value = Array.isArray(response.logs) ? response.logs : []
        // 更新日志信息
        accessLogInfo.value = {
          nginx_version: response.nginx_version || null,
          nginx_version_detail: response.nginx_version_detail || null,
          log_path: response.log_path || null,
          log_size_bytes: response.log_size_bytes ?? null,
          active_version: response.active_version || null,
          install_path: response.install_path || null,
          binary: response.binary || null
        }
        // 更新当前查看的分片文件信息
        currentAccessRotateFile.value = response.is_rotate_file ? response.rotate_file : null
        // 更新是否还有更多更早的日志
        const pagination = response.pagination || {}
        const totalPages = pagination.total_pages || 1
        accessHasMore.value = accessPage.value < totalPages
      } else {
        accessLogs.value = []
        if (response && response.success === false) {
          ElMessage.warning(response.detail || '未获取到访问日志数据')
        }
      }
    } else {
      // 重置为第一页，默认查看最近的 1000 行
      errorPage.value = 1
      const keyword = errorFilters.value.keyword || null
      const startDate = errorFilters.value.dateRange?.[0] || null
      const endDate = errorFilters.value.dateRange?.[1] || null
      const rotateFile = errorFilters.value.selectedRotateFile || null
      const response = await logsApi.getErrorLogs(errorPage.value, ERROR_PAGE_SIZE, keyword, startDate, endDate, rotateFile)
      console.log('错误日志响应:', response)
      if (response && response.success !== false) {
        errorLogs.value = Array.isArray(response.logs) ? response.logs : []
        // 更新日志信息
        errorLogInfo.value = {
          nginx_version: response.nginx_version || null,
          nginx_version_detail: response.nginx_version_detail || null,
          log_path: response.log_path || null,
          log_size_bytes: response.log_size_bytes ?? null,
          active_version: response.active_version || null,
          install_path: response.install_path || null,
          binary: response.binary || null
        }
        // 更新当前查看的分片文件信息
        currentErrorRotateFile.value = response.is_rotate_file ? response.rotate_file : null
        // 更新是否还有更多更早的日志
        const pagination = response.pagination || {}
        const totalPages = pagination.total_pages || 1
        errorHasMore.value = errorPage.value < totalPages
      } else {
        errorLogs.value = []
        if (response && response.success === false) {
          ElMessage.warning(response.detail || '未获取到错误日志数据')
        }
      }
    }
  } catch (error) {
    console.error('加载日志失败:', error)
    const errorMsg = error?.detail || error?.message || '加载日志失败'
    ElMessage.error(errorMsg)
    if (activeTab.value === 'access') {
      accessLogs.value = []
    } else {
      errorLogs.value = []
    }
  } finally {
    loading.value = false
  }
}

// 加载更多（更早）的访问日志
const loadMoreAccess = async () => {
  if (!accessHasMore.value || loading.value) return
  loading.value = true
  try {
    accessPage.value += 1
    const keyword = accessFilters.value.keyword || null
    const startDate = accessFilters.value.dateRange?.[0] || null
    const endDate = accessFilters.value.dateRange?.[1] || null
    const rotateFile = accessFilters.value.selectedRotateFile || null
    const response = await logsApi.getAccessLogs(accessPage.value, ACCESS_PAGE_SIZE, keyword, startDate, endDate, rotateFile)
    console.log('访问日志（加载更多）响应:', response)
    if (response && response.success !== false) {
      const newLogs = Array.isArray(response.logs) ? response.logs : []
      // 更早的日志追加到当前列表顶部
      accessLogs.value = [...newLogs, ...accessLogs.value]
      const pagination = response.pagination || {}
      const totalPages = pagination.total_pages || 1
      accessHasMore.value = accessPage.value < totalPages
    } else {
      accessPage.value -= 1
      if (response && response.success === false) {
        ElMessage.warning(response.detail || '未获取到更多访问日志数据')
      }
    }
  } catch (error) {
    accessPage.value -= 1
    console.error('加载更多访问日志失败:', error)
    const errorMsg = error?.detail || error?.message || '加载更多访问日志失败'
    ElMessage.error(errorMsg)
  } finally {
    loading.value = false
  }
}

// 加载更多（更早）的错误日志
const loadMoreError = async () => {
  if (!errorHasMore.value || loading.value) return
  loading.value = true
  try {
    errorPage.value += 1
    const keyword = errorFilters.value.keyword || null
    const startDate = errorFilters.value.dateRange?.[0] || null
    const endDate = errorFilters.value.dateRange?.[1] || null
    const rotateFile = errorFilters.value.selectedRotateFile || null
    const response = await logsApi.getErrorLogs(errorPage.value, ERROR_PAGE_SIZE, keyword, startDate, endDate, rotateFile)
    console.log('错误日志（加载更多）响应:', response)
    if (response && response.success !== false) {
      const newLogs = Array.isArray(response.logs) ? response.logs : []
      errorLogs.value = [...newLogs, ...errorLogs.value]
      const pagination = response.pagination || {}
      const totalPages = pagination.total_pages || 1
      errorHasMore.value = errorPage.value < totalPages
    } else {
      errorPage.value -= 1
      if (response && response.success === false) {
        ElMessage.warning(response.detail || '未获取到更多错误日志数据')
      }
    }
  } catch (error) {
    errorPage.value -= 1
    console.error('加载更多错误日志失败:', error)
    const errorMsg = error?.detail || error?.message || '加载更多错误日志失败'
    ElMessage.error(errorMsg)
  } finally {
    loading.value = false
  }
}

const handleAccessSearch = () => {
  loadLogs()
}

const handleAccessReset = () => {
  accessFilters.value = { keyword: '', dateRange: null, selectedRotateFile: null }
  currentAccessRotateFile.value = null
  loadLogs()
}

const handleErrorSearch = () => {
  loadLogs()
}

const handleErrorReset = () => {
  errorFilters.value = { keyword: '', dateRange: null, selectedRotateFile: null }
  currentErrorRotateFile.value = null
  loadLogs()
}

// 选择访问日志分片
const selectAccessRotateFile = (file) => {
  // 如果已选中，则取消选择，返回查看当前日志
  if (accessFilters.value.selectedRotateFile === file.filename) {
    accessFilters.value.selectedRotateFile = null
    accessFilters.value.dateRange = null
  } else {
    // 选中该分片文件
    accessFilters.value.selectedRotateFile = file.filename
    // 清除日期范围，因为查看分片文件时不需要日期过滤
    accessFilters.value.dateRange = null
  }
  // 重置页码并重新加载日志
  accessPage.value = 1
  handleAccessSearch()
}

// 选择错误日志分片
const selectErrorRotateFile = (file) => {
  // 如果已选中，则取消选择，返回查看当前日志
  if (errorFilters.value.selectedRotateFile === file.filename) {
    errorFilters.value.selectedRotateFile = null
    errorFilters.value.dateRange = null
  } else {
    // 选中该分片文件
    errorFilters.value.selectedRotateFile = file.filename
    // 清除日期范围，因为查看分片文件时不需要日期过滤
    errorFilters.value.dateRange = null
  }
  // 重置页码并重新加载日志
  errorPage.value = 1
  handleErrorSearch()
}

const setAccessQuickTime = (minutes) => {
  const now = new Date()
  const startTime = new Date(now.getTime() - minutes * 60 * 1000)
  
  accessFilters.value.dateRange = [
    formatDateTime(startTime),
    formatDateTime(now)
  ]
  handleAccessSearch()
}

const setErrorQuickTime = (minutes) => {
  const now = new Date()
  const startTime = new Date(now.getTime() - minutes * 60 * 1000)
  
  errorFilters.value.dateRange = [
    formatDateTime(startTime),
    formatDateTime(now)
  ]
  handleErrorSearch()
}

// 加载日志分片文件列表
const loadRotateFiles = async () => {
  try {
    const response = await logsApi.getLogRotateFiles()
    if (response && response.success) {
      accessRotateFiles.value = response.access_files || []
      errorRotateFiles.value = response.error_files || []
    }
  } catch (error) {
    console.error('加载日志分片文件列表失败:', error)
  }
}

// 手动触发日志轮转
const handleRotateLogs = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要立即进行日志分片吗？当前日志将被重命名为带日期的文件。',
      '确认分片',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    
    rotating.value = true
    try {
      const response = await logsApi.triggerLogRotate()
      if (response && response.success) {
        ElMessage.success('日志分片完成')
        // 刷新日志和分片列表
        await loadLogs()
        await loadRotateFiles()
      } else {
        ElMessage.error(response?.message || '日志分片失败')
      }
    } catch (error) {
      const errorMsg = error?.response?.data?.detail?.message || error?.message || '日志分片失败'
      ElMessage.error(errorMsg)
    } finally {
      rotating.value = false
    }
  } catch (error) {
    // 用户取消
    if (error !== 'cancel') {
      console.error('日志分片失败:', error)
    }
  }
}

// 删除访问日志分片
const deleteAccessRotateFile = async (file) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除分片文件 "${file.filename}" 吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    
    try {
      await logsApi.deleteLogRotateFile(file.filename)
      ElMessage.success('分片文件已删除')
      
      // 如果删除的是当前查看的分片，清除选择并返回当前日志
      if (accessFilters.value.selectedRotateFile === file.filename) {
        accessFilters.value.selectedRotateFile = null
        currentAccessRotateFile.value = null
      }
      
      // 刷新分片列表和日志
      await loadRotateFiles()
      await loadLogs()
    } catch (error) {
      const errorMsg = error?.response?.data?.detail || error?.message || '删除分片文件失败'
      ElMessage.error(errorMsg)
    }
  } catch (error) {
    // 用户取消
    if (error !== 'cancel') {
      console.error('删除分片文件失败:', error)
    }
  }
}

// 删除错误日志分片
const deleteErrorRotateFile = async (file) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除分片文件 "${file.filename}" 吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    
    try {
      await logsApi.deleteLogRotateFile(file.filename)
      ElMessage.success('分片文件已删除')
      
      // 如果删除的是当前查看的分片，清除选择并返回当前日志
      if (errorFilters.value.selectedRotateFile === file.filename) {
        errorFilters.value.selectedRotateFile = null
        currentErrorRotateFile.value = null
      }
      
      // 刷新分片列表和日志
      await loadRotateFiles()
      await loadLogs()
    } catch (error) {
      const errorMsg = error?.response?.data?.detail || error?.message || '删除分片文件失败'
      ElMessage.error(errorMsg)
    }
  } catch (error) {
    // 用户取消
    if (error !== 'cancel') {
      console.error('删除分片文件失败:', error)
    }
  }
}

watch(activeTab, () => {
  loadLogs()
})

onMounted(() => {
  loadLogs()
  loadRotateFiles()
})
</script>

<style scoped>
.logs-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.log-info {
  margin-bottom: 15px;
}

.log-filters {
  margin-bottom: 15px;
  padding: 15px;
  background-color: var(--bg-tertiary);
  border-radius: 4px;
  border: 1px solid var(--border-color);
}

.filter-form {
  margin: 0;
}

.filter-form .el-form-item {
  margin-bottom: 10px;
}

.quick-time-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.quick-time-buttons .el-button {
  margin: 0;
}

.log-path {
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.text-muted {
  color: var(--text-muted);
  font-style: italic;
  font-size: 12px;
}

.log-content {
  min-height: 500px;
  max-height: calc(100vh - 400px);
  display: flex;
  flex-direction: column;
}

.empty-log {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 500px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
}

.logs-tabs :deep(.el-tabs__header) {
  margin-bottom: 15px;
}

.logs-tabs :deep(.el-tabs__nav-wrap) {
  padding: 0;
}

.logs-tabs :deep(.el-tabs__nav) {
  display: flex;
  gap: 12px;
  width: 100%;
}

.logs-tabs :deep(.el-tabs__item) {
  flex: 1;
  text-align: center;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 10px 0;
  transition: all 0.2s ease;
}

.logs-tabs :deep(.el-tabs__item.is-active) {
  background-color: var(--nginx-green);
  color: var(--text-white) !important;
  border-color: var(--nginx-green);
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(0, 150, 57, 0.35);
}

.logs-tabs :deep(.el-tabs__item:not(.is-active):hover) {
  border-color: var(--nginx-green);
  color: var(--nginx-green) !important;
}

.logs-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

.version-tag {
  max-width: 220px;
  display: inline-flex;
  align-items: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.load-more-wrapper {
  margin-top: 10px;
  display: flex;
  justify-content: center;
}

.log-rotate-section {
  margin-top: 15px;
  margin-bottom: 15px;
  padding: 10px;
  background-color: var(--bg-tertiary);
  border-radius: 4px;
  border: 1px solid var(--border-color);
}

.rotate-files-header {
  margin-bottom: 8px;
}

.rotate-files-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.rotate-files-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rotate-file-tag {
  cursor: default;
  margin-right: 6px;
  margin-bottom: 6px;
}

.rotate-file-tag :deep(.el-tag__close) {
  margin-left: 4px;
}

.rotate-file-indicator {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

</style>


