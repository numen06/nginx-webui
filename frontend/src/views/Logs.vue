<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Clock3,
  FileText,
  Maximize2,
  Minimize2,
  RefreshCw,
  RotateCw,
  Search,
  Server,
  X,
} from 'lucide-vue-next'
import { logsApi } from '../api/logs'
import { ElMessage, ElMessageBox } from '@/lib/feedback'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import LogViewer from '../components/LogViewer.vue'
import { formatDateTime } from '../utils/date'

type LogTab = 'access' | 'error'

interface LogInfo {
  nginx_version: string | null
  nginx_version_detail: string | null
  log_path: string | null
  log_size_bytes: number | null
  active_version: string | null
  install_path: string | null
  binary: string | null
}

interface LogFilters {
  keyword: string
  dateRange: string[] | null
  selectedRotateFile: string | null
}

interface RotateFile {
  filename: string
  date?: string
  size?: number
}

const emptyLogInfo = (): LogInfo => ({
  nginx_version: null,
  nginx_version_detail: null,
  log_path: null,
  log_size_bytes: null,
  active_version: null,
  install_path: null,
  binary: null,
})

const emptyFilters = (): LogFilters => ({
  keyword: '',
  dateRange: null,
  selectedRotateFile: null,
})

const formatFileSize = (bytes?: number | null) => {
  if (bytes === 0) return '0 B'
  if (bytes == null || Number.isNaN(bytes)) return '-'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), sizes.length - 1)
  const value = bytes / Math.pow(1024, index)
  return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${sizes[index]}`
}

const apiErrorMessage = (error: any, fallback: string) =>
  error?.response?.data?.detail?.message
  || error?.response?.data?.detail
  || error?.detail
  || error?.message
  || fallback

const activeTab = ref<LogTab>('access')
const focusMode = ref(false)
const loading = ref(false)
const rotating = ref(false)
const quickRange = ref('')

const accessLogs = ref<string[]>([])
const errorLogs = ref<string[]>([])
const accessLogInfo = ref<LogInfo>(emptyLogInfo())
const errorLogInfo = ref<LogInfo>(emptyLogInfo())
const accessFilters = ref<LogFilters>(emptyFilters())
const errorFilters = ref<LogFilters>(emptyFilters())
const currentAccessRotateFile = ref<string | null>(null)
const currentErrorRotateFile = ref<string | null>(null)
const accessRotateFiles = ref<RotateFile[]>([])
const errorRotateFiles = ref<RotateFile[]>([])

const PAGE_SIZE = 100
const accessPage = ref(1)
const errorPage = ref(1)
const accessHasMore = ref(false)
const errorHasMore = ref(false)

const activeLogs = computed(() => activeTab.value === 'access' ? accessLogs.value : errorLogs.value)
const activeLogInfo = computed(() => activeTab.value === 'access' ? accessLogInfo.value : errorLogInfo.value)
const activeFilters = computed(() => activeTab.value === 'access' ? accessFilters.value : errorFilters.value)
const activeRotateFiles = computed(() => activeTab.value === 'access' ? accessRotateFiles.value : errorRotateFiles.value)
const currentRotateFile = computed(() => activeTab.value === 'access' ? currentAccessRotateFile.value : currentErrorRotateFile.value)
const activeHasMore = computed(() => activeTab.value === 'access' ? accessHasMore.value : errorHasMore.value)
const activeTitle = computed(() => activeTab.value === 'access' ? '访问日志' : '错误日志')
const activeFilename = computed(() => activeTab.value === 'access' ? 'access-log' : 'error-log')
const currentLogPath = computed(() => currentRotateFile.value || activeLogInfo.value.log_path || '日志路径未知')

const applyResponse = (response: any, tab: LogTab) => {
  const logs = Array.isArray(response.logs) ? response.logs : []
  const info: LogInfo = {
    nginx_version: response.nginx_version || null,
    nginx_version_detail: response.nginx_version_detail || null,
    log_path: response.log_path || null,
    log_size_bytes: response.log_size_bytes ?? null,
    active_version: response.active_version || null,
    install_path: response.install_path || null,
    binary: response.binary || null,
  }
  const totalPages = response.pagination?.total_pages || 1

  if (tab === 'access') {
    accessLogs.value = logs
    accessLogInfo.value = info
    currentAccessRotateFile.value = response.is_rotate_file ? response.rotate_file : null
    accessHasMore.value = accessPage.value < totalPages
  } else {
    errorLogs.value = logs
    errorLogInfo.value = info
    currentErrorRotateFile.value = response.is_rotate_file ? response.rotate_file : null
    errorHasMore.value = errorPage.value < totalPages
  }
}

const loadLogs = async () => {
  const tab = activeTab.value
  const filters = tab === 'access' ? accessFilters.value : errorFilters.value
  const page = tab === 'access' ? accessPage : errorPage
  page.value = 1
  loading.value = true

  try {
    const args = [
      page.value,
      PAGE_SIZE,
      filters.keyword || null,
      filters.dateRange?.[0] || null,
      filters.dateRange?.[1] || null,
      filters.selectedRotateFile || null,
    ] as const
    const response = tab === 'access'
      ? await logsApi.getAccessLogs(...args)
      : await logsApi.getErrorLogs(...args)

    if (response && response.success !== false) {
      applyResponse(response, tab)
    } else {
      if (tab === 'access') accessLogs.value = []
      else errorLogs.value = []
      ElMessage.warning(response?.detail || `未获取到${activeTitle.value}数据`)
    }
  } catch (error) {
    console.error('加载日志失败:', error)
    if (tab === 'access') accessLogs.value = []
    else errorLogs.value = []
    ElMessage.error(apiErrorMessage(error, '加载日志失败'))
  } finally {
    loading.value = false
  }
}

const loadMore = async () => {
  const tab = activeTab.value
  const hasMore = tab === 'access' ? accessHasMore : errorHasMore
  const page = tab === 'access' ? accessPage : errorPage
  const filters = tab === 'access' ? accessFilters.value : errorFilters.value
  if (!hasMore.value || loading.value) return

  loading.value = true
  page.value += 1
  try {
    const args = [
      page.value,
      PAGE_SIZE,
      filters.keyword || null,
      filters.dateRange?.[0] || null,
      filters.dateRange?.[1] || null,
      filters.selectedRotateFile || null,
    ] as const
    const response = tab === 'access'
      ? await logsApi.getAccessLogs(...args)
      : await logsApi.getErrorLogs(...args)

    if (response && response.success !== false) {
      const earlierLogs = Array.isArray(response.logs) ? response.logs : []
      const totalPages = response.pagination?.total_pages || 1
      if (tab === 'access') {
        accessLogs.value = [...earlierLogs, ...accessLogs.value]
        accessHasMore.value = page.value < totalPages
      } else {
        errorLogs.value = [...earlierLogs, ...errorLogs.value]
        errorHasMore.value = page.value < totalPages
      }
    } else {
      page.value -= 1
      ElMessage.warning(response?.detail || '未获取到更多日志')
    }
  } catch (error) {
    page.value -= 1
    ElMessage.error(apiErrorMessage(error, '加载更多日志失败'))
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  quickRange.value = ''
  if (activeTab.value === 'access') {
    accessFilters.value = emptyFilters()
    currentAccessRotateFile.value = null
  } else {
    errorFilters.value = emptyFilters()
    currentErrorRotateFile.value = null
  }
  loadLogs()
}

const setQuickTime = () => {
  const minutes = Number(quickRange.value)
  if (!minutes) return
  const now = new Date()
  const startTime = new Date(now.getTime() - minutes * 60 * 1000)
  activeFilters.value.dateRange = [formatDateTime(startTime), formatDateTime(now)]
  activeFilters.value.selectedRotateFile = null
  loadLogs()
  quickRange.value = ''
}

const selectRotateFile = (file: RotateFile) => {
  const filters = activeFilters.value
  filters.selectedRotateFile = filters.selectedRotateFile === file.filename ? null : file.filename
  filters.dateRange = null
  quickRange.value = ''
  loadLogs()
}

const returnToCurrentLog = () => {
  activeFilters.value.selectedRotateFile = null
  activeFilters.value.dateRange = null
  quickRange.value = ''
  loadLogs()
}

const loadRotateFiles = async () => {
  try {
    const response = await logsApi.getLogRotateFiles()
    if (response?.success) {
      accessRotateFiles.value = response.access_files || []
      errorRotateFiles.value = response.error_files || []
    }
  } catch (error) {
    console.error('加载日志分片文件列表失败:', error)
  }
}

const handleRotateLogs = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要立即进行日志分片吗？当前日志将被重命名为带日期的文件。',
      '确认分片',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
    rotating.value = true
    const response = await logsApi.triggerLogRotate()
    if (!response?.success) {
      ElMessage.error(response?.message || '日志分片失败')
      return
    }
    ElMessage.success('日志分片完成')
    await Promise.all([loadLogs(), loadRotateFiles()])
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '日志分片失败'))
  } finally {
    rotating.value = false
  }
}

const deleteRotateFile = async (file: RotateFile) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除分片文件 “${file.filename}” 吗？此操作不可恢复。`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
    await logsApi.deleteLogRotateFile(file.filename)
    if (accessFilters.value.selectedRotateFile === file.filename) {
      accessFilters.value.selectedRotateFile = null
      currentAccessRotateFile.value = null
    }
    if (errorFilters.value.selectedRotateFile === file.filename) {
      errorFilters.value.selectedRotateFile = null
      currentErrorRotateFile.value = null
    }
    ElMessage.success('分片文件已删除')
    await Promise.all([loadRotateFiles(), loadLogs()])
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '删除分片文件失败'))
  }
}

watch(activeTab, () => {
  quickRange.value = ''
  loadLogs()
})

watch(quickRange, (value) => {
  if (value) setQuickTime()
})

onMounted(() => {
  loadLogs()
  loadRotateFiles()
})
</script>

<template>
  <div
    class="logs-page page-shell max-w-none lg:h-full lg:min-h-0 lg:overflow-hidden"
    :class="focusMode ? 'gap-2 p-2 md:p-3' : 'gap-3 p-3 md:p-4'"
    :data-focus-mode="focusMode"
  >
    <div v-if="!focusMode" class="page-heading shrink-0 gap-4">
      <div>
        <h2 class="page-title">日志查看</h2>
        <p class="page-description">筛选、查看和下载 Nginx 运行日志，快速定位访问与错误信息。</p>
      </div>
    </div>

    <Card class="logs-workspace gap-0 overflow-hidden py-0 lg:min-h-0 lg:flex-1">
      <div class="workspace-header">
        <Tabs v-model="activeTab" class="shrink-0 gap-0">
          <TabsList class="grid w-full grid-cols-2 sm:w-64">
            <TabsTrigger value="access">访问日志</TabsTrigger>
            <TabsTrigger value="error">错误日志</TabsTrigger>
          </TabsList>
        </Tabs>

        <div class="log-status" :title="currentLogPath">
          <Badge :variant="currentRotateFile ? 'secondary' : 'default'">
            {{ currentRotateFile ? '历史分片' : '当前日志' }}
          </Badge>
          <FileText class="size-4 shrink-0 text-muted-foreground" />
          <span class="min-w-0 truncate font-mono text-xs">{{ currentLogPath }}</span>
          <span class="hidden shrink-0 text-xs text-muted-foreground md:inline">
            {{ formatFileSize(activeLogInfo.log_size_bytes) }}
          </span>
          <span v-if="activeLogInfo.nginx_version" class="hidden shrink-0 text-xs text-muted-foreground 2xl:inline">
            · {{ activeLogInfo.nginx_version }}
          </span>
        </div>

        <div class="header-actions">
          <Button v-if="currentRotateFile" size="sm" variant="ghost" @click="returnToCurrentLog">
            返回当前日志
          </Button>
          <Button size="sm" variant="outline" :disabled="rotating" @click="handleRotateLogs">
            <RotateCw :class="['size-4', { 'animate-spin': rotating }]" />
            <span class="hidden sm:inline">立即分片</span>
          </Button>
          <Button size="icon-sm" variant="outline" :disabled="loading" title="刷新日志" aria-label="刷新日志" @click="loadLogs">
            <RefreshCw :class="['size-4', { 'animate-spin': loading }]" />
          </Button>
          <Button
            size="sm"
            variant="outline"
            :aria-pressed="focusMode"
            :aria-label="focusMode ? '退出专注查看' : '进入专注查看'"
            @click="focusMode = !focusMode"
          >
            <Minimize2 v-if="focusMode" class="size-4" />
            <Maximize2 v-else class="size-4" />
            <span class="hidden xl:inline">{{ focusMode ? '退出专注' : '专注查看' }}</span>
          </Button>
        </div>
      </div>

      <div class="filter-toolbar">
        <div class="relative min-w-0 flex-1 sm:min-w-56 sm:max-w-sm">
          <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            v-model="activeFilters.keyword"
            class="pl-9"
            placeholder="搜索日志内容"
            aria-label="搜索日志内容"
            @keyup.enter="loadLogs"
          />
        </div>
        <ui-date-picker
          v-model="activeFilters.dateRange"
          class="log-date-picker"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          format="YYYY-MM-DD HH:mm:ss"
          value-format="YYYY-MM-DD HH:mm:ss"
          :disabled="Boolean(activeFilters.selectedRotateFile)"
          @change="loadLogs"
        />
        <NativeSelect v-model="quickRange" class="w-full sm:w-32" aria-label="快捷时间范围">
          <NativeSelectOption value="">快捷时间</NativeSelectOption>
          <NativeSelectOption value="15">最近 15 分钟</NativeSelectOption>
          <NativeSelectOption value="30">最近 30 分钟</NativeSelectOption>
          <NativeSelectOption value="60">最近 1 小时</NativeSelectOption>
          <NativeSelectOption value="180">最近 3 小时</NativeSelectOption>
          <NativeSelectOption value="360">最近 6 小时</NativeSelectOption>
          <NativeSelectOption value="720">最近 12 小时</NativeSelectOption>
          <NativeSelectOption value="1440">最近 1 天</NativeSelectOption>
          <NativeSelectOption value="10080">最近 7 天</NativeSelectOption>
        </NativeSelect>
        <Button size="sm" @click="loadLogs"><Search class="size-4" />搜索</Button>
        <Button size="sm" variant="ghost" @click="resetFilters"><RefreshCw class="size-4" />重置</Button>
      </div>

      <div v-if="!focusMode && activeRotateFiles.length" class="rotate-strip">
        <div class="rotate-strip-label">
          <Clock3 class="size-4" />历史分片 {{ activeRotateFiles.length }}
        </div>
        <div class="rotate-files" role="list" :aria-label="`${activeTitle}历史分片`">
          <div
            v-for="file in activeRotateFiles"
            :key="file.filename"
            :class="['rotate-file', { 'is-active': activeFilters.selectedRotateFile === file.filename }]"
            :title="`${file.filename} · ${formatFileSize(file.size)}`"
            role="listitem"
          >
            <button type="button" class="rotate-file-main" @click="selectRotateFile(file)">
              <span class="truncate">{{ file.date || file.filename }}</span>
              <span class="text-[10px] opacity-60">{{ formatFileSize(file.size) }}</span>
            </button>
            <button
              type="button"
              class="rotate-file-delete"
              :aria-label="`删除分片 ${file.filename}`"
              @click="deleteRotateFile(file)"
            >
              <X class="size-3" />
            </button>
          </div>
        </div>
      </div>

      <div v-if="!focusMode && activeLogInfo.install_path" class="runtime-strip" :title="activeLogInfo.nginx_version_detail || ''">
        <Server class="size-4 shrink-0 text-primary" />
        <span class="shrink-0 font-medium">Nginx 运行目录</span>
        <span class="min-w-0 truncate font-mono text-muted-foreground">{{ activeLogInfo.install_path }}</span>
      </div>

      <div v-loading="loading" class="log-panel">
        <div v-if="!loading && activeLogs.length === 0" class="empty-log">
          <FileText class="size-8 opacity-30" />
          <div class="font-medium">暂无{{ activeTitle }}</div>
          <div class="text-xs text-muted-foreground">可以调整时间范围或清空筛选条件后重试</div>
        </div>
        <LogViewer
          v-else
          :key="activeTab"
          :logs="activeLogs"
          :keyword="activeFilters.keyword"
          :show-line-numbers="true"
          :filename="activeFilename"
        />
      </div>

      <div v-if="activeHasMore && !loading && activeLogs.length" class="load-more-wrapper">
        <Button size="sm" variant="ghost" @click="loadMore">加载更早的 100 行</Button>
      </div>
    </Card>
  </div>
</template>

<style scoped>
.logs-workspace {
  min-width: 0;
}

.workspace-header {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  border-bottom: 1px solid var(--border);
  padding: 0.625rem;
}

.log-status {
  display: flex;
  min-width: 0;
  flex: 1 1 18rem;
  align-items: center;
  gap: 0.5rem;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.filter-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--muted) 18%, transparent);
  padding: 0.625rem;
}

.log-date-picker {
  width: min(23rem, 100%);
}

.filter-toolbar :deep(.ui-date-editor) {
  height: 2.25rem;
  border-radius: 0.375rem;
}

.rotate-strip {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
  border-bottom: 1px solid var(--border);
  padding: 0.5rem 0.625rem;
}

.rotate-strip-label {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--muted-foreground);
}

.rotate-files {
  display: flex;
  min-width: 0;
  flex: 1;
  gap: 0.375rem;
  overflow-x: auto;
  padding-bottom: 0.125rem;
  scrollbar-width: thin;
}

.rotate-file {
  display: inline-flex;
  max-width: 15rem;
  flex: 0 0 auto;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  background: var(--background);
  font-size: 0.75rem;
  color: var(--muted-foreground);
  transition: border-color 0.15s ease, background-color 0.15s ease, color 0.15s ease;
}

.rotate-file:hover,
.rotate-file.is-active {
  border-color: color-mix(in srgb, var(--primary) 55%, var(--border));
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  color: var(--foreground);
}

.rotate-file-main {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.375rem;
  padding: 0.3rem 0.35rem 0.3rem 0.55rem;
}

.rotate-file-main:focus-visible {
  border-radius: 0.3rem;
  outline: 2px solid var(--ring);
  outline-offset: -2px;
}

.rotate-file-delete {
  display: inline-grid;
  width: 1.125rem;
  height: 1.125rem;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 0.25rem;
  margin-right: 0.3rem;
}

.rotate-file-delete:hover,
.rotate-file-delete:focus-visible {
  background: color-mix(in srgb, var(--destructive) 18%, transparent);
  color: var(--destructive);
  outline: none;
}

.runtime-strip {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.5rem;
  border-bottom: 1px solid var(--border);
  padding: 0.4rem 0.75rem;
  font-size: 0.75rem;
}

.log-panel {
  display: flex;
  min-width: 0;
  min-height: 32rem;
  flex: 1;
  flex-direction: column;
  padding: 0.625rem;
}

.empty-log {
  display: grid;
  min-height: 30rem;
  flex: 1;
  place-content: center;
  justify-items: center;
  gap: 0.5rem;
  border: 1px dashed var(--border);
  border-radius: 0.5rem;
  text-align: center;
  color: var(--muted-foreground);
}

.load-more-wrapper {
  display: flex;
  flex: 0 0 auto;
  justify-content: center;
  border-top: 1px solid var(--border);
  padding: 0.375rem;
}

@media (min-width: 1024px) {
  .logs-workspace {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .log-panel {
    min-height: 0;
    overflow: hidden;
  }

  .empty-log {
    min-height: 0;
  }
}

@media (max-width: 767px) {
  .workspace-header > [data-slot='tabs'] {
    width: 100%;
  }

  .log-status {
    order: 2;
    flex-basis: 100%;
  }

  .header-actions {
    margin-left: auto;
  }

  .filter-toolbar > * {
    flex: 1 1 auto;
  }

  .log-date-picker {
    width: 100%;
  }

  .rotate-strip {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.4rem;
  }

  .rotate-files {
    width: 100%;
  }

  .log-panel {
    min-height: 30rem;
    padding: 0.5rem;
  }
}
</style>
