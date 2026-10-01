<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  Archive,
  CheckCircle2,
  Eye,
  FileCode2,
  Folder,
  FolderPlus,
  Maximize2,
  Minimize2,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Scissors,
  Search,
  Server,
  Sparkles,
  TestTube2,
  Trash2,
  Upload,
  X,
} from 'lucide-vue-next'
import { apiErrorMessage } from '@/api'
import {
  configApi,
  type ConfigEntry,
  type ConfigInfoResponse,
  type ConfigTestResponse,
} from '@/api/config'
import MonacoEditor from '@/components/MonacoEditor.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { ElMessage, ElMessageBox } from '@/lib/feedback'
import { formatDateTime } from '@/utils/date'

interface ConfigInfo {
  nginx_version: string | null
  nginx_version_detail: string | null
  config_path: string | null
  config_dir: string | null
  active_version: string | null
  install_path: string | null
  binary: string | null
  pending_changes: boolean
}

interface SiteItem {
  path: string
  label: string
}

interface BackupOption {
  id: number
  label: string
}

type SidebarTab = 'sites' | 'files'

const EMPTY_CONFIG_INFO: ConfigInfo = {
  nginx_version: null,
  nginx_version_detail: null,
  config_path: null,
  config_dir: null,
  active_version: null,
  install_path: null,
  binary: null,
  pending_changes: false,
}

const configContent = ref('')
const originalContent = ref('')
const currentFilePath = ref('')
const isModified = ref(false)
const loading = ref(true)
const saving = ref(false)
const applying = ref(false)
const backupLoading = ref(false)
const pageError = ref('')
const selectedBackupId = ref('')
const backupOptions = ref<BackupOption[]>([])
const sidebarTab = ref<SidebarTab>('sites')
const flatEntries = ref<ConfigEntry[]>([])
const siteItems = ref<SiteItem[]>([])
const siteKeyword = ref('')
const previewVisible = ref(false)
const previewContent = ref('')
const focusMode = ref(false)
const configInfo = ref<ConfigInfo>({ ...EMPTY_CONFIG_INFO })

const filteredSites = computed(() => {
  const query = siteKeyword.value.trim().toLowerCase()
  if (!query) return siteItems.value
  return siteItems.value.filter(site =>
    site.label.toLowerCase().includes(query) || site.path.toLowerCase().includes(query),
  )
})

const filteredEntries = computed(() => {
  const query = siteKeyword.value.trim().toLowerCase()
  return [...flatEntries.value]
    .filter(entry => !query
      || entry.path.toLowerCase().includes(query)
      || entry.name?.toLowerCase().includes(query))
    .sort((a, b) => a.path.localeCompare(b.path))
})

const selectedSiteVisible = computed(() => filteredSites.value.some(site => site.path === currentFilePath.value))

function entryDepth(entry: ConfigEntry): number {
  return Math.max(0, entry.path.split('/').length - 1)
}

function parseSiteLabel(path: string, content: string): string {
  const match = content.match(/^\s*server_name\s+([^;]+);/m)
  if (!match) return path.split('/').pop() || path
  return match[1]?.split(/\s+/).filter(Boolean).join(', ') || path
}

function normalizeConfigInfo(response: ConfigInfoResponse): ConfigInfo {
  return {
    nginx_version: response.nginx_version || null,
    nginx_version_detail: response.nginx_version_detail || null,
    config_path: response.config_path || null,
    config_dir: response.config_dir || null,
    active_version: response.active_version || null,
    install_path: response.install_path || null,
    binary: response.binary || null,
    pending_changes: Boolean(response.pending_changes),
  }
}

async function loadTreeAndSites() {
  const treeResponse = await configApi.getTree()
  flatEntries.value = treeResponse.files || []

  const confFiles = flatEntries.value
    .filter(item => !item.is_dir && item.path.startsWith('conf.d/') && item.path.endsWith('.conf'))
    .sort((a, b) => a.path.localeCompare(b.path))
  const fileResults = await Promise.allSettled(confFiles.map(item => configApi.getFile(item.path)))

  siteItems.value = confFiles.map((item, index) => {
    const result = fileResults[index]
    if (result?.status === 'fulfilled') {
      return { path: item.path, label: parseSiteLabel(item.path, result.value.content || '') }
    }
    return { path: item.path, label: item.name || item.path.split('/').pop() || item.path }
  })
}

function findDefaultFile(): string {
  if (siteItems.value.length > 0) return siteItems.value[0]?.path || ''
  if (flatEntries.value.some(item => item.path === 'nginx.conf')) return 'nginx.conf'
  return flatEntries.value.find(item => !item.is_dir)?.path || ''
}

async function openFile(path: string, options: { reload?: boolean; discardChanges?: boolean } = {}) {
  if (!path || (path === currentFilePath.value && !options.reload)) return
  if (isModified.value && !options.discardChanges) {
    try {
      await ElMessageBox.confirm('当前文件有未保存修改，切换文件将放弃这些修改。是否继续？', '未保存的修改')
    } catch {
      return
    }
  }

  try {
    const response = await configApi.getFile(path)
    currentFilePath.value = response.path || path
    configContent.value = response.content || ''
    originalContent.value = configContent.value
    isModified.value = false
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '读取配置文件失败'))
  }
}

async function loadConfig() {
  loading.value = true
  pageError.value = ''
  try {
    const response = await configApi.getConfig()
    configInfo.value = normalizeConfigInfo(response)
    await loadTreeAndSites()
    const preferred = currentFilePath.value || findDefaultFile()
    if (preferred) {
      await openFile(preferred, { discardChanges: true, reload: true })
    } else {
      configContent.value = ''
      originalContent.value = ''
      currentFilePath.value = ''
      isModified.value = false
    }
  } catch (error) {
    pageError.value = apiErrorMessage(error, '加载配置失败')
    ElMessage.error(pageError.value)
  } finally {
    loading.value = false
  }
}

function handleContentChange() {
  isModified.value = configContent.value !== originalContent.value
}

async function handleSave(): Promise<boolean> {
  if (!currentFilePath.value || saving.value) return false
  saving.value = true
  try {
    await configApi.updateFile(currentFilePath.value, configContent.value)
    originalContent.value = configContent.value
    isModified.value = false
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    ElMessage.success('配置已保存到工作副本')
    return true
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '保存配置失败'))
    return false
  } finally {
    saving.value = false
  }
}

async function saveIfModified(): Promise<boolean> {
  return isModified.value ? handleSave() : true
}

function handleSaveShortcut(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    void handleSave()
  }
}

async function handleFormat() {
  if (!currentFilePath.value) return
  const original = configContent.value
  try {
    const response = await configApi.formatConfig(configContent.value)
    if (response.success && response.formatted?.trim()) {
      configContent.value = response.formatted
      isModified.value = configContent.value !== originalContent.value
      ElMessage.success('配置已格式化')
    } else {
      configContent.value = original
      ElMessage.warning(response.message || '格式化失败，已保留原配置')
    }
  } catch (error) {
    configContent.value = original
    ElMessage.error(apiErrorMessage(error, '格式化配置失败，已保留原配置'))
  }
}

function showTestResult(response: ConfigTestResponse, titlePrefix: string) {
  if (response.success) {
    const warningText = response.warnings?.length ? `，但有 ${response.warnings.length} 个警告` : ''
    ElMessage.success(`${titlePrefix}成功${warningText}`)
    if (response.warnings?.length) {
      void ElMessageBox.alert(response.warnings.join('\n\n'), `${titlePrefix}警告`)
    }
    return
  }

  let message = response.message || `${titlePrefix}失败`
  if (response.errors?.length) message += `\n\n详细错误信息：\n\n${response.errors.join('\n\n')}`
  if (response.output?.trim()) message += `\n\n完整输出：\n${response.output}`
  void ElMessageBox.alert(message, `${titlePrefix}失败`)
}

async function handleValidate() {
  if (!currentFilePath.value) return
  try {
    showTestResult(await configApi.validateFile(currentFilePath.value, configContent.value), '配置校验')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '校验配置失败'))
  }
}

async function handleTest() {
  try {
    if (!await saveIfModified()) return
    showTestResult(await configApi.testConfig(), '配置测试')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '测试配置失败'))
  }
}

async function handleApply() {
  if (applying.value || !await saveIfModified()) return
  try {
    await ElMessageBox.confirm(
      '强制覆盖会将工作副本覆盖到实际配置目录，但不会重载 Nginx。是否继续？',
      '强制覆盖确认',
      { confirmButtonText: '覆盖配置', cancelButtonText: '取消' },
    )
    applying.value = true
    const response = await configApi.applyConfig()
    if (!response.success) {
      showTestResult(response.test_result || response, '强制覆盖')
      return
    }
    configInfo.value.pending_changes = false
    ElMessage.success(response.message || '配置目录已覆盖，建议重启 Nginx')
    await Promise.all([loadConfig(), handleLoadBackups()])
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '强制覆盖配置失败'))
  } finally {
    applying.value = false
  }
}

async function handleReload() {
  try {
    if (!await saveIfModified()) return
    await ElMessageBox.confirm('测试通过后将覆盖线上配置并重新装载 Nginx，是否继续？', '重新装载配置')
    const response = await configApi.reloadConfig()
    if (!response.success) {
      showTestResult(response.test_result || response, '配置重载')
      return
    }
    const backupInfo = response.backup_id ? `，已创建备份 #${response.backup_id}` : ''
    ElMessage.success(`配置重载成功${backupInfo}`)
    await Promise.all([loadConfig(), handleLoadBackups()])
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '重新装载配置失败'))
  }
}

function sanitizeFileName(value: string): string {
  const cleaned = value.trim().toLowerCase().replace(/^\*\./, 'wildcard-').replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '')
  return cleaned || 'default'
}

async function handleNewSite() {
  try {
    const { value } = await ElMessageBox.prompt('请输入站点域名', '新建站点', {
      inputPlaceholder: 'example.com',
      confirmButtonText: '创建',
      cancelButtonText: '取消',
    })
    const domain = String(value).trim()
    if (!domain) {
      ElMessage.warning('域名不能为空')
      return
    }
    const path = `conf.d/${sanitizeFileName(domain)}.conf`
    const content = `server {\n    listen 80;\n    server_name ${domain};\n\n    root html;\n    index index.html index.htm;\n\n    location / {\n        try_files $uri $uri/ =404;\n    }\n}\n`
    await configApi.updateFile(path, content)
    configInfo.value.pending_changes = true
    siteKeyword.value = ''
    await loadTreeAndSites()
    await openFile(path, { discardChanges: true })
    sidebarTab.value = 'sites'
    ElMessage.success('站点配置已创建')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '创建站点失败'))
  }
}

async function handleNewFile() {
  try {
    const { value } = await ElMessageBox.prompt('请输入配置文件路径', '新建文件', {
      inputValue: 'conf.d/new-site.conf',
      confirmButtonText: '创建',
      cancelButtonText: '取消',
    })
    const path = String(value).trim()
    if (!path) return
    await configApi.updateFile(path, '')
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    await openFile(path, { discardChanges: true })
    ElMessage.success('配置文件已创建')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '创建文件失败'))
  }
}

async function handleNewDir() {
  const parent = currentFilePath.value.includes('/')
    ? currentFilePath.value.split('/').slice(0, -1).join('/')
    : ''
  try {
    const { value } = await ElMessageBox.prompt('请输入目录名称', '新建目录', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
    })
    const name = String(value).trim()
    if (!name || /[/\\]/.test(name)) {
      ElMessage.warning('目录名不能为空，且不能包含 / 或 \\')
      return
    }
    await configApi.createDirectory(parent, name)
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    ElMessage.success('目录已创建')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '创建目录失败'))
  }
}

async function handleRename() {
  if (!currentFilePath.value || currentFilePath.value === 'nginx.conf') return
  const oldName = currentFilePath.value.split('/').pop() || ''
  try {
    const { value } = await ElMessageBox.prompt('请输入新名称', '重命名', {
      inputValue: oldName,
      confirmButtonText: '重命名',
      cancelButtonText: '取消',
    })
    const name = String(value).trim()
    if (!name || /[/\\]/.test(name)) {
      ElMessage.warning('名称不能为空，且不能包含 / 或 \\')
      return
    }
    const response = await configApi.renamePath(currentFilePath.value, name)
    const nextPath = response.entry?.path
    if (!nextPath) throw new Error('接口未返回重命名后的路径')
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    await openFile(nextPath, { discardChanges: true })
    ElMessage.success('重命名成功')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '重命名失败'))
  }
}

async function handleDelete() {
  if (!currentFilePath.value || currentFilePath.value === 'nginx.conf') return
  try {
    await ElMessageBox.confirm(`确定删除“${currentFilePath.value}”吗？此操作不可恢复。`, '删除配置')
    await configApi.deletePath(currentFilePath.value)
    currentFilePath.value = ''
    configContent.value = ''
    originalContent.value = ''
    isModified.value = false
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    const nextFile = findDefaultFile()
    if (nextFile) await openFile(nextFile, { discardChanges: true })
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '删除失败'))
  }
}

async function handleSplitLegacy() {
  try {
    if (!await saveIfModified()) return
    await ElMessageBox.confirm(
      '拆分会保留 nginx.conf.legacy，并将 server 配置拆到 conf.d。是否继续？',
      '拆分老配置',
    )
    const response = await configApi.splitLegacyConfig()
    await loadConfig()
    ElMessage.success(response.test_result?.success ? `${response.message || '拆分完成'}，测试通过` : response.message || '拆分完成')
    if (response.test_result && !response.test_result.success) showTestResult(response.test_result, '拆分后配置测试')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '拆分配置失败'))
  }
}

async function handleMergedPreview() {
  try {
    if (!await saveIfModified()) return
    const response = await configApi.getMergedPreview()
    previewContent.value = response.content || ''
    previewVisible.value = true
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '生成合并预览失败'))
  }
}

async function handleLoadBackups() {
  backupLoading.value = true
  try {
    const response = await configApi.getBackups()
    backupOptions.value = (response.backups || []).map(item => ({
      id: item.id,
      label: `${item.created_at ? formatDateTime(item.created_at) : '未知时间'} · #${item.id}${item.is_last_version ? ' · 当前线上版本' : ''}`,
    }))
    selectedBackupId.value = backupOptions.value[0]?.id.toString() || ''
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '获取备份列表失败'))
  } finally {
    backupLoading.value = false
  }
}

async function handleCreateBackup() {
  backupLoading.value = true
  try {
    const response = await configApi.createBackup()
    if (!response.success) {
      ElMessage.error(response.message || '备份创建失败')
      return
    }
    ElMessage.success('当前线上配置已备份')
    await handleLoadBackups()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '创建备份失败'))
  } finally {
    backupLoading.value = false
  }
}

async function handleRollback() {
  const backupId = Number(selectedBackupId.value)
  if (!backupId) {
    ElMessage.warning('请先选择备份版本')
    return
  }
  try {
    await ElMessageBox.confirm('回滚会覆盖当前工作副本，是否继续？', '回滚配置')
    backupLoading.value = true
    const response = await configApi.restoreBackup(backupId)
    if (!response.success) {
      ElMessage.error(response.message || '回滚失败')
      return
    }
    ElMessage.success('配置已回滚到所选版本')
    await Promise.all([loadConfig(), handleLoadBackups()])
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '回滚失败'))
  } finally {
    backupLoading.value = false
  }
}

onMounted(async () => {
  await Promise.allSettled([loadConfig(), handleLoadBackups()])
  window.addEventListener('keydown', handleSaveShortcut)
})

onBeforeUnmount(() => window.removeEventListener('keydown', handleSaveShortcut))
</script>

<template>
  <div
    class="page-shell max-w-none lg:h-full lg:min-h-0 lg:overflow-hidden"
    :class="focusMode ? 'gap-2 p-2 md:p-3' : 'gap-3 p-3 md:p-4'"
    :data-focus-mode="focusMode"
  >
    <div v-if="!focusMode" class="page-heading shrink-0 gap-4">
      <div>
        <h2 class="page-title">配置管理</h2>
        <p class="page-description">编辑工作副本、校验配置并安全同步到运行中的 Nginx。</p>
      </div>
      <div class="toolbar">
        <Button variant="outline" :disabled="loading" @click="loadConfig">
          <RefreshCw :class="['size-4', { 'animate-spin': loading }]" />刷新
        </Button>
        <Button variant="secondary" @click="handleTest"><TestTube2 class="size-4" />测试</Button>
        <div class="config-save-actions flex flex-wrap items-center gap-1 rounded-lg border bg-muted/20 p-1">
          <Button :disabled="!currentFilePath || saving" @click="handleSave">
            <Save class="size-4" />{{ saving ? '保存中' : '保存' }}
          </Button>
          <Button variant="outline" :disabled="applying" @click="handleApply">
            <Upload class="size-4" />{{ applying ? '覆盖中' : '强制覆盖' }}
          </Button>
        </div>
        <Button variant="outline" @click="handleReload"><RefreshCw class="size-4" />重新装载</Button>
      </div>
    </div>

    <div v-if="pageError" class="flex shrink-0 items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-red-200">
      <Server class="mt-0.5 size-4 shrink-0" />
      <div><div class="font-medium">配置数据加载失败</div><div class="mt-1 text-red-200/80">{{ pageError }}</div></div>
    </div>

    <Card v-if="!focusMode" class="shrink-0 gap-0 py-0">
      <CardContent class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 p-2">
        <div class="flex min-w-0 flex-1 items-center gap-2 text-xs">
          <Server class="size-4 shrink-0 text-primary" />
          <Badge :variant="configInfo.pending_changes ? 'secondary' : 'default'">
            {{ configInfo.pending_changes ? '待应用' : '已同步' }}
          </Badge>
          <span class="shrink-0 font-medium">Nginx {{ loading ? '加载中' : (configInfo.nginx_version || '未知') }}</span>
          <span class="hidden text-muted-foreground xl:inline">·</span>
          <span class="hidden min-w-0 truncate font-mono text-muted-foreground xl:inline" :title="configInfo.config_dir || ''">
            配置 {{ configInfo.config_dir || '未知' }}
          </span>
          <span class="hidden min-w-0 truncate font-mono text-muted-foreground 2xl:inline" :title="configInfo.install_path || ''">
            · 安装 {{ configInfo.install_path || '系统安装' }}
          </span>
        </div>
        <div class="flex min-w-0 flex-1 items-center justify-end gap-2 sm:flex-none">
          <Archive class="hidden size-4 shrink-0 text-muted-foreground sm:block" />
          <NativeSelect v-model="selectedBackupId" class="h-8 w-full sm:w-56" :disabled="backupLoading || !backupOptions.length" aria-label="选择配置备份">
            <NativeSelectOption value="">{{ backupOptions.length ? '选择备份版本' : '暂无备份' }}</NativeSelectOption>
            <NativeSelectOption v-for="item in backupOptions" :key="item.id" :value="item.id.toString()">{{ item.label }}</NativeSelectOption>
          </NativeSelect>
          <Button size="icon-sm" variant="outline" :disabled="backupLoading" title="刷新备份" aria-label="刷新备份" @click="handleLoadBackups"><RefreshCw class="size-4" /></Button>
          <Button size="icon-sm" variant="outline" :disabled="backupLoading" title="创建备份" aria-label="创建备份" @click="handleCreateBackup"><Plus class="size-4" /></Button>
          <Button size="icon-sm" variant="outline" :disabled="backupLoading || !selectedBackupId" title="回滚备份" aria-label="回滚备份" @click="handleRollback"><RotateCcw class="size-4" /></Button>
        </div>
      </CardContent>
    </Card>

    <Card class="overflow-hidden gap-0 py-0 lg:min-h-0 lg:flex-1">
      <div class="flex shrink-0 flex-wrap items-center gap-2 border-b bg-muted/10 p-2">
        <Button size="sm" @click="handleNewSite"><Plus class="size-4" />新建站点</Button>
        <Button size="sm" variant="outline" @click="handleNewFile"><FileCode2 class="size-4" />新建文件</Button>
        <Button size="sm" variant="outline" @click="handleNewDir"><FolderPlus class="size-4" /><span class="hidden sm:inline">新建目录</span></Button>
        <Button size="sm" variant="outline" :disabled="!currentFilePath || currentFilePath === 'nginx.conf'" @click="handleRename"><Pencil class="size-4" /><span class="hidden sm:inline">重命名</span></Button>
        <Button size="sm" variant="destructive" :disabled="!currentFilePath || currentFilePath === 'nginx.conf'" @click="handleDelete"><Trash2 class="size-4" /><span class="hidden sm:inline">删除</span></Button>
        <span class="hidden flex-1 md:block" />
        <Button v-if="focusMode" size="sm" variant="secondary" @click="handleTest"><TestTube2 class="size-4" /><span class="hidden lg:inline">测试</span></Button>
        <div v-if="focusMode" class="config-save-actions flex items-center gap-1 rounded-lg border bg-muted/20 p-1">
          <Button size="sm" :disabled="!currentFilePath || saving" @click="handleSave"><Save class="size-4" />{{ saving ? '保存中' : '保存' }}</Button>
          <Button size="sm" variant="outline" :disabled="applying" @click="handleApply"><Upload class="size-4" />{{ applying ? '覆盖中' : '强制覆盖' }}</Button>
        </div>
        <Button v-if="focusMode" size="sm" variant="outline" @click="handleReload"><RefreshCw class="size-4" /><span class="hidden xl:inline">重新装载</span></Button>
        <Button size="sm" variant="outline" @click="handleSplitLegacy"><Scissors class="size-4" />拆分老配置</Button>
        <Button size="icon-sm" variant="ghost" title="合并预览" aria-label="合并预览" @click="handleMergedPreview"><Eye class="size-4" /></Button>
        <Button
          size="sm"
          variant="outline"
          :aria-pressed="focusMode"
          :aria-label="focusMode ? '退出专注编辑' : '进入专注编辑'"
          @click="focusMode = !focusMode"
        >
          <Minimize2 v-if="focusMode" class="size-4" />
          <Maximize2 v-else class="size-4" />
          <span class="hidden sm:inline">{{ focusMode ? '退出专注' : '专注编辑' }}</span>
        </Button>
      </div>
      <div
        class="grid min-w-0 lg:min-h-0 lg:flex-1"
        :class="focusMode ? 'lg:grid-cols-1' : 'lg:grid-cols-[300px_minmax(0,1fr)]'"
      >
        <aside v-if="!focusMode" class="min-w-0 border-b bg-muted/15 lg:min-h-0 lg:overflow-hidden lg:border-r lg:border-b-0">
          <Tabs v-model="sidebarTab" class="gap-0 lg:flex lg:h-full lg:min-h-0 lg:flex-col">
            <div class="shrink-0 space-y-3 border-b p-3">
              <TabsList class="grid w-full grid-cols-2">
                <TabsTrigger value="sites">站点配置 <span class="ml-1 text-xs opacity-60">{{ siteItems.length }}</span></TabsTrigger>
                <TabsTrigger value="files">文件树 <span class="ml-1 text-xs opacity-60">{{ flatEntries.length }}</span></TabsTrigger>
              </TabsList>
              <div class="relative">
                <Search class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input v-model="siteKeyword" class="pr-9 pl-9" :placeholder="sidebarTab === 'sites' ? '筛选域名或文件路径' : '筛选配置文件'" aria-label="筛选站点配置" />
                <button v-if="siteKeyword" type="button" class="absolute right-2 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="清空筛选" @click="siteKeyword = ''"><X class="size-3.5" /></button>
              </div>
              <div class="flex items-center justify-between text-xs text-muted-foreground">
                <span v-if="sidebarTab === 'sites'">显示 {{ filteredSites.length }} / {{ siteItems.length }} 个站点</span>
                <span v-else>显示 {{ filteredEntries.length }} / {{ flatEntries.length }} 项</span>
                <span v-if="sidebarTab === 'sites' && currentFilePath && !selectedSiteVisible">当前文件不在筛选结果中</span>
              </div>
            </div>

            <TabsContent value="sites" class="m-0 lg:min-h-0 lg:flex-1 lg:overflow-hidden">
              <ScrollArea class="h-[420px] lg:h-full">
                <div class="space-y-1 p-2">
                  <button
                    v-for="site in filteredSites"
                    :key="site.path"
                    type="button"
                    :class="['w-full rounded-md border px-3 py-2.5 text-left transition-colors', site.path === currentFilePath ? 'border-primary/50 bg-primary/10' : 'border-transparent hover:border-border hover:bg-muted/60']"
                    @click="openFile(site.path)"
                  >
                    <span :class="['block truncate text-sm font-medium', site.path === currentFilePath ? 'text-primary' : 'text-foreground']">{{ site.label }}</span>
                    <span class="mt-1 block truncate font-mono text-[11px] text-muted-foreground">{{ site.path }}</span>
                  </button>
                  <div v-if="!filteredSites.length" class="grid min-h-40 place-items-center px-4 text-center text-sm text-muted-foreground">
                    <div><Search class="mx-auto mb-2 size-5 opacity-50" />{{ siteItems.length ? '没有匹配的站点配置' : '暂无站点配置' }}</div>
                  </div>
                </div>
              </ScrollArea>
            </TabsContent>

            <TabsContent value="files" class="m-0 lg:min-h-0 lg:flex-1 lg:overflow-hidden">
              <ScrollArea class="h-[420px] lg:h-full">
                <div class="space-y-0.5 p-2">
                  <button
                    v-for="entry in filteredEntries"
                    :key="entry.path"
                    type="button"
                    :disabled="entry.is_dir"
                    :class="['flex w-full items-center gap-2 rounded-md py-2 pr-2 text-left text-sm transition-colors', entry.path === currentFilePath ? 'bg-primary/10 text-primary' : 'hover:bg-muted/60', entry.is_dir ? 'cursor-default text-muted-foreground' : 'cursor-pointer']"
                    :style="{ paddingLeft: `${12 + entryDepth(entry) * 14}px` }"
                    @click="!entry.is_dir && openFile(entry.path)"
                  >
                    <Folder v-if="entry.is_dir" class="size-4 shrink-0" />
                    <FileCode2 v-else class="size-4 shrink-0" />
                    <span class="truncate">{{ entry.name || entry.path.split('/').pop() }}</span>
                  </button>
                  <div v-if="!filteredEntries.length" class="grid min-h-40 place-items-center text-sm text-muted-foreground">没有匹配的配置文件</div>
                </div>
              </ScrollArea>
            </TabsContent>
          </Tabs>
        </aside>

        <main class="flex min-w-0 flex-col p-3 lg:min-h-0 lg:overflow-hidden">
          <div class="mb-3 flex shrink-0 flex-wrap items-center justify-between gap-3">
            <div class="min-w-0">
              <div class="flex min-w-0 items-center gap-2">
                <FileCode2 class="size-4 shrink-0 text-primary" />
                <span class="truncate font-mono text-sm font-medium">{{ currentFilePath || '未选择文件' }}</span>
                <Badge v-if="isModified" variant="secondary">未保存</Badge>
              </div>
              <div v-if="currentFilePath" class="mt-1 text-xs text-muted-foreground">工作副本 · Ctrl/Cmd + S 保存</div>
            </div>
            <div class="flex gap-2">
              <Button size="sm" variant="outline" :disabled="!currentFilePath" @click="handleFormat"><Sparkles class="size-4" />格式化</Button>
              <Button size="sm" variant="outline" :disabled="!currentFilePath" @click="handleValidate"><CheckCircle2 class="size-4" />校验</Button>
            </div>
          </div>
          <MonacoEditor v-if="currentFilePath" v-model="configContent" class="min-h-[480px] flex-1 lg:min-h-0" language="nginx" height="100%" @change="handleContentChange" />
          <div v-else class="grid min-h-[480px] flex-1 place-items-center rounded-md border border-dashed text-sm text-muted-foreground lg:min-h-0">
            <div class="text-center"><FileCode2 class="mx-auto mb-2 size-7 opacity-40" />请选择一个配置文件</div>
          </div>
        </main>
      </div>
      <div v-if="!focusMode" class="flex shrink-0 items-start gap-3 border-t bg-primary/5 px-4 py-2 text-xs text-muted-foreground">
        <Server class="mt-0.5 size-4 shrink-0 text-primary" />
        <span>保存只更新工作副本；“重新装载”会先测试配置，成功后自动备份并覆盖线上配置。</span>
      </div>
    </Card>

    <Dialog v-model:open="previewVisible">
      <DialogContent class="max-h-[88vh] max-w-5xl overflow-hidden">
        <DialogHeader><DialogTitle>合并配置预览</DialogTitle><DialogDescription>工作副本展开 include 后的完整配置，仅供检查。</DialogDescription></DialogHeader>
        <pre class="max-h-[68vh] overflow-auto rounded-md border bg-[#0b0f14] p-4 font-mono text-xs leading-5 text-slate-200">{{ previewContent || '暂无预览内容' }}</pre>
        <DialogFooter><Button @click="previewVisible = false">关闭</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
