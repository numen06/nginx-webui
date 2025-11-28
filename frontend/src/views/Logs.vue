<template>
  <div class="logs-page">
    <el-tabs v-model="activeTab" class="logs-tabs" stretch>
      <el-tab-pane label="访问日志" name="access">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>访问日志</span>
              <el-button 
                :icon="Refresh" 
                circle 
                size="small" 
                @click="loadLogs"
                :loading="loading"
              />
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
                <el-text v-if="accessLogInfo.log_path" class="log-path" size="small">
                  {{ accessLogInfo.log_path }}
                </el-text>
                <span v-else class="text-muted">未知</span>
              </el-descriptions-item>
              <el-descriptions-item v-if="accessLogInfo.nginx_version_detail" label="版本详情" :span="2">
                <el-text type="info" size="small">{{ accessLogInfo.nginx_version_detail }}</el-text>
              </el-descriptions-item>
            </el-descriptions>
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
                <el-button type="primary" @click="handleAccessSearch">搜索</el-button>
                <el-button type="info" @click="handleAccessReset">重置</el-button>
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
          </div>
        </el-card>
      </el-tab-pane>
      <el-tab-pane label="错误日志" name="error">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>错误日志</span>
              <el-button 
                :icon="Refresh" 
                circle 
                size="small" 
                @click="loadLogs"
                :loading="loading"
              />
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
                <el-text v-if="errorLogInfo.log_path" class="log-path" size="small">
                  {{ errorLogInfo.log_path }}
                </el-text>
                <span v-else class="text-muted">未知</span>
              </el-descriptions-item>
              <el-descriptions-item v-if="errorLogInfo.nginx_version_detail" label="版本详情" :span="2">
                <el-text type="info" size="small">{{ errorLogInfo.nginx_version_detail }}</el-text>
              </el-descriptions-item>
            </el-descriptions>
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
                <el-button type="primary" @click="handleErrorSearch">搜索</el-button>
                <el-button type="info" @click="handleErrorReset">重置</el-button>
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
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { logsApi } from '../api/logs'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import LogViewer from '../components/LogViewer.vue'

const activeTab = ref('access')
const loading = ref(false)
const accessLogs = ref([])
const errorLogs = ref([])
const accessLogInfo = ref({
  nginx_version: null,
  nginx_version_detail: null,
  log_path: null,
  active_version: null,
  install_path: null,
  binary: null
})
const errorLogInfo = ref({
  nginx_version: null,
  nginx_version_detail: null,
  log_path: null,
  active_version: null,
  install_path: null,
  binary: null
})
const accessFilters = ref({
  keyword: '',
  dateRange: null
})
const errorFilters = ref({
  keyword: '',
  dateRange: null
})
const accessLogViewerRef = ref(null)
const errorLogViewerRef = ref(null)
const MAX_VERSION_LABEL_LENGTH = 20

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
      const keyword = accessFilters.value.keyword || null
      const startDate = accessFilters.value.dateRange?.[0] || null
      const endDate = accessFilters.value.dateRange?.[1] || null
      // 使用最大允许的page_size来获取日志（后端限制为1000）
      const response = await logsApi.getAccessLogs(1, 1000, keyword, startDate, endDate)
      console.log('访问日志响应:', response)
      if (response && response.success !== false) {
        accessLogs.value = Array.isArray(response.logs) ? response.logs : []
        // 更新日志信息
        accessLogInfo.value = {
          nginx_version: response.nginx_version || null,
          nginx_version_detail: response.nginx_version_detail || null,
          log_path: response.log_path || null,
          active_version: response.active_version || null,
          install_path: response.install_path || null,
          binary: response.binary || null
        }
      } else {
        accessLogs.value = []
        if (response && response.success === false) {
          ElMessage.warning(response.detail || '未获取到访问日志数据')
        }
      }
    } else {
      const keyword = errorFilters.value.keyword || null
      const startDate = errorFilters.value.dateRange?.[0] || null
      const endDate = errorFilters.value.dateRange?.[1] || null
      // 使用较大的page_size来获取日志（后端限制为50000）
      const response = await logsApi.getErrorLogs(1, 50000, keyword, startDate, endDate)
      console.log('错误日志响应:', response)
      if (response && response.success !== false) {
        errorLogs.value = Array.isArray(response.logs) ? response.logs : []
        // 更新日志信息
        errorLogInfo.value = {
          nginx_version: response.nginx_version || null,
          nginx_version_detail: response.nginx_version_detail || null,
          log_path: response.log_path || null,
          active_version: response.active_version || null,
          install_path: response.install_path || null,
          binary: response.binary || null
        }
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

const handleAccessSearch = () => {
  loadLogs()
}

const handleAccessReset = () => {
  accessFilters.value = { keyword: '', dateRange: null }
  loadLogs()
}

const handleErrorSearch = () => {
  loadLogs()
}

const handleErrorReset = () => {
  errorFilters.value = { keyword: '', dateRange: null }
  loadLogs()
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

const formatDateTime = (date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}


watch(activeTab, () => {
  loadLogs()
})

onMounted(() => {
  loadLogs()
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

</style>


