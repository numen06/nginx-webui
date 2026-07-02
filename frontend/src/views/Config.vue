<template>
  <div class="config-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Nginx 配置</span>
          <div class="header-actions">
            <el-button type="info" @click="handleFormat" :disabled="!currentFilePath">
              <el-icon><MagicStick /></el-icon>
              <span class="btn-label">格式化</span>
            </el-button>
            <el-button type="cyan" @click="handleValidate" :disabled="!currentFilePath">
              <el-icon><Finished /></el-icon>
              <span class="btn-label">校验配置</span>
            </el-button>
            <el-button type="purple" @click="handleTest">
              <el-icon><Cpu /></el-icon>
              <span class="btn-label">测试配置</span>
            </el-button>
            <el-button type="success" @click="handleSave" :loading="saving" :disabled="!currentFilePath">
              <el-icon><DocumentChecked /></el-icon>
              <span class="btn-label">保存</span>
            </el-button>
            <el-button type="orange" @click="handleApply" :loading="applying">
              <el-icon><Upload /></el-icon>
              <span class="btn-label">强制覆盖</span>
            </el-button>
            <el-button type="warning" @click="handleReload">
              <el-icon><Refresh /></el-icon>
              <span class="btn-label">重新装载</span>
            </el-button>
          </div>
        </div>
      </template>

      <div class="config-info">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item v-if="configInfo.install_path" label="当前 Nginx 目录">
            <el-text type="info" size="small">{{ configInfo.install_path }}</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="当前 Nginx 版本">
            <el-tag v-if="configInfo.nginx_version" type="info" size="small">
              {{ configInfo.nginx_version }}
            </el-tag>
            <span v-else class="text-muted">未知</span>
          </el-descriptions-item>
          <el-descriptions-item label="配置目录" :span="2">
            <el-text v-if="configInfo.config_dir" class="config-path" size="small">
              {{ configInfo.config_dir }}
            </el-text>
            <span v-else class="text-muted">未知</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="configInfo.binary" label="可执行文件路径" :span="2">
            <el-text type="info" size="small">{{ configInfo.binary }}</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="临时配置状态">
            <el-tag :type="configInfo.pending_changes ? 'warning' : 'success'" size="small">
              {{ configInfo.pending_changes ? '存在未应用的修改' : '已与运行版本同步' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="配置备份版本" :span="2">
            <div class="backup-row">
              <el-select
                v-model="selectedBackupId"
                placeholder="选择一个备份版本（最多显示最近 10 个）"
                class="backup-select"
                :disabled="backupLoading || backupOptions.length === 0"
              >
                <el-option
                  v-for="item in backupOptions"
                  :key="item.id"
                  :label="item.label"
                  :value="item.id"
                />
              </el-select>
              <el-button class="backup-btn" @click="handleLoadBackups" :loading="backupLoading" link>
                <el-icon><RefreshRight /></el-icon>
                <span class="btn-label">刷新</span>
              </el-button>
              <el-button type="primary" class="backup-btn" @click="handleCreateBackup" :loading="backupLoading">
                <el-icon><DocumentAdd /></el-icon>
                <span class="btn-label">备份当前线上配置</span>
              </el-button>
              <el-button type="warning" class="backup-btn" :disabled="!selectedBackupId" @click="handleRollback">
                <el-icon><RefreshLeft /></el-icon>
                <span class="btn-label">回滚到所选版本</span>
              </el-button>
            </div>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="config-toolbar">
        <el-button type="primary" @click="handleNewSite">
          <el-icon><DocumentAdd /></el-icon>
          <span class="btn-label">新建站点</span>
        </el-button>
        <el-button @click="handleNewFile">
          <el-icon><DocumentAdd /></el-icon>
          <span class="btn-label">新建文件</span>
        </el-button>
        <el-button @click="handleNewDir">
          <el-icon><FolderAdd /></el-icon>
          <span class="btn-label">新建目录</span>
        </el-button>
        <el-button @click="handleRename" :disabled="!currentFilePath || currentFilePath === 'nginx.conf'">
          <el-icon><Edit /></el-icon>
          <span class="btn-label">重命名</span>
        </el-button>
        <el-button type="danger" @click="handleDelete" :disabled="!currentFilePath || currentFilePath === 'nginx.conf'">
          <el-icon><Delete /></el-icon>
          <span class="btn-label">删除</span>
        </el-button>
        <el-button type="warning" @click="handleSplitLegacy">
          <el-icon><Scissor /></el-icon>
          <span class="btn-label">拆分老配置</span>
        </el-button>
        <el-button @click="handleMergedPreview">
          <el-icon><View /></el-icon>
          <span class="btn-label">合并预览</span>
        </el-button>
      </div>

      <div class="config-workspace">
        <aside class="config-sidebar">
          <el-tabs v-model="sidebarTab" stretch>
            <el-tab-pane label="站点配置" name="sites">
              <el-scrollbar height="620px">
                <div
                  v-for="site in siteItems"
                  :key="site.path"
                  class="site-item"
                  :class="{ active: site.path === currentFilePath }"
                  @click="openFile(site.path)"
                >
                  <span class="site-name">{{ site.label }}</span>
                  <span class="site-path">{{ site.path }}</span>
                </div>
                <el-empty v-if="siteItems.length === 0" description="暂无站点配置" :image-size="72" />
              </el-scrollbar>
            </el-tab-pane>
            <el-tab-pane label="文件树" name="files">
              <el-scrollbar height="620px">
                <el-tree
                  class="config-tree"
                  :data="fileTree"
                  node-key="path"
                  :props="treeProps"
                  default-expand-all
                  highlight-current
                  @node-click="handleTreeNodeClick"
                />
              </el-scrollbar>
            </el-tab-pane>
          </el-tabs>
        </aside>

        <main class="editor-panel">
          <div class="editor-header">
            <div>
              <span class="current-file">{{ currentFilePath || '未选择文件' }}</span>
              <el-tag v-if="isModified" type="warning" size="small">未保存</el-tag>
            </div>
            <el-text v-if="currentFilePath" type="info" size="small">工作副本</el-text>
          </div>
          <MonacoEditor
            v-if="currentFilePath"
            v-model="configContent"
            language="nginx"
            height="620px"
            @change="handleContentChange"
          />
          <el-empty v-else description="请选择一个配置文件" />
        </main>
      </div>

      <el-alert class="working-copy-alert" type="info" show-icon :closable="false">
        <template #title>配置目录临时副本模式</template>
        <p class="working-copy-text">
          保存后仅更新工作副本，测试通过后点击“重新装载”才会覆盖线上 conf/ 配置目录并自动备份。
        </p>
      </el-alert>
    </el-card>

    <el-dialog v-model="previewVisible" title="合并预览" width="80%">
      <pre class="preview-content">{{ previewContent }}</pre>
      <template #footer>
        <el-button type="primary" @click="previewVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { configApi } from '../api/config'
import MonacoEditor from '../components/MonacoEditor.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTime } from '../utils/date'
import {
  MagicStick,
  Finished,
  Cpu,
  DocumentChecked,
  Refresh,
  RefreshRight,
  DocumentAdd,
  RefreshLeft,
  Upload,
  Edit,
  Delete,
  FolderAdd,
  View,
  Scissor
} from '@element-plus/icons-vue'

const configContent = ref('')
const originalContent = ref('')
const currentFilePath = ref('')
const isModified = ref(false)
const saving = ref(false)
const applying = ref(false)
const backupLoading = ref(false)
const selectedBackupId = ref(null)
const backupOptions = ref([])
const sidebarTab = ref('sites')
const flatEntries = ref([])
const siteItems = ref([])
const previewVisible = ref(false)
const previewContent = ref('')

const configInfo = ref({
  nginx_version: null,
  nginx_version_detail: null,
  config_path: null,
  config_dir: null,
  active_version: null,
  install_path: null,
  binary: null,
  pending_changes: false
})

const treeProps = {
  children: 'children',
  label: 'label'
}

const fileTree = computed(() => buildTree(flatEntries.value))

onMounted(async () => {
  await loadConfig()
  await handleLoadBackups()
  window.addEventListener('keydown', handleSaveShortcut)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleSaveShortcut)
})

const buildTree = (entries) => {
  const root = []
  const nodes = new Map()
  const sorted = [...entries].sort((a, b) => a.path.localeCompare(b.path))

  for (const entry of sorted) {
    const parts = entry.path.split('/')
    const label = parts[parts.length - 1]
    const node = {
      ...entry,
      label,
      children: []
    }
    nodes.set(entry.path, node)
    const parentPath = parts.slice(0, -1).join('/')
    if (parentPath && nodes.has(parentPath)) {
      nodes.get(parentPath).children.push(node)
    } else {
      root.push(node)
    }
  }
  return root
}

const parseSiteLabel = (path, content) => {
  const match = content.match(/^\s*server_name\s+([^;]+);/m)
  if (!match) return path.split('/').pop()
  return match[1].split(/\s+/).filter(Boolean).join(', ')
}

const loadConfig = async () => {
  try {
    const response = await configApi.getConfig()
    configInfo.value = {
      nginx_version: response.nginx_version || null,
      nginx_version_detail: response.nginx_version_detail || null,
      config_path: response.config_path || null,
      config_dir: response.config_dir || null,
      active_version: response.active_version || null,
      install_path: response.install_path || null,
      binary: response.binary || null,
      pending_changes: Boolean(response.pending_changes)
    }

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
    console.error('加载配置失败:', error)
    ElMessage.error(error?.detail || error?.message || '加载配置失败')
  }
}

const loadTreeAndSites = async () => {
  const treeResponse = await configApi.getTree()
  flatEntries.value = treeResponse.files || []

  const confFiles = flatEntries.value
    .filter((item) => !item.is_dir && item.path.startsWith('conf.d/') && item.path.endsWith('.conf'))
    .sort((a, b) => a.path.localeCompare(b.path))

  const sites = []
  for (const item of confFiles) {
    try {
      const file = await configApi.getFile(item.path)
      sites.push({
        path: item.path,
        label: parseSiteLabel(item.path, file.content || '')
      })
    } catch {
      sites.push({ path: item.path, label: item.name })
    }
  }
  siteItems.value = sites
}

const findDefaultFile = () => {
  if (siteItems.value.length > 0) return siteItems.value[0].path
  if (flatEntries.value.some((item) => item.path === 'nginx.conf')) return 'nginx.conf'
  const firstFile = flatEntries.value.find((item) => !item.is_dir)
  return firstFile?.path || ''
}

const openFile = async (path, options = {}) => {
  if (!path) return
  if (path === currentFilePath.value && !options.reload) return
  if (isModified.value && !options.discardChanges) {
    try {
      await ElMessageBox.confirm('当前文件有未保存修改，切换文件将放弃这些修改。是否继续？', '未保存的修改', {
        type: 'warning'
      })
    } catch {
      return
    }
  }

  const response = await configApi.getFile(path)
  currentFilePath.value = response.path || path
  configContent.value = response.content || ''
  originalContent.value = configContent.value
  isModified.value = false
}

const handleTreeNodeClick = (node) => {
  if (!node.is_dir) {
    openFile(node.path)
  }
}

const handleContentChange = () => {
  isModified.value = configContent.value !== originalContent.value
}

const handleSave = async () => {
  if (!currentFilePath.value || saving.value) return
  saving.value = true
  try {
    await configApi.updateFile(currentFilePath.value, configContent.value)
    originalContent.value = configContent.value
    isModified.value = false
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    ElMessage.success('配置已保存到临时副本')
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || '保存配置失败')
  } finally {
    saving.value = false
  }
}

const saveIfModified = async () => {
  if (isModified.value) {
    await handleSave()
  }
}

const handleSaveShortcut = (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    handleSave()
  }
}

const handleFormat = async () => {
  if (!currentFilePath.value) return
  const original = configContent.value
  try {
    const response = await configApi.formatConfig(configContent.value)
    if (response.success && response.formatted?.trim()) {
      configContent.value = response.formatted
      isModified.value = true
      ElMessage.success('配置已格式化')
    } else {
      configContent.value = original
      ElMessage.warning(response.message || '格式化失败，已保留原配置')
    }
  } catch {
    configContent.value = original
    ElMessage.error('格式化配置失败，已保留原配置')
  }
}

const showTestResult = (response, titlePrefix) => {
  if (response.success) {
    const warningText = response.warnings?.length ? `，但有 ${response.warnings.length} 个警告` : ''
    ElMessage.success(`${titlePrefix}成功${warningText}`)
    if (response.warnings?.length) {
      ElMessageBox.alert(response.warnings.join('\n\n'), `${titlePrefix}警告`, { type: 'warning' })
    }
    return
  }

  let message = response.message || `${titlePrefix}失败`
  if (response.errors?.length) {
    message += '\n\n详细错误信息：\n\n' + response.errors.join('\n\n')
  }
  if (response.output?.trim()) {
    message += '\n\n完整输出：\n' + response.output
  }
  ElMessageBox.alert(message, `${titlePrefix}失败`, {
    type: 'error',
    confirmButtonText: '确定',
    customClass: 'error-dialog'
  })
}

const handleValidate = async () => {
  if (!currentFilePath.value) return
  try {
    const response = await configApi.validateFile(currentFilePath.value, configContent.value)
    showTestResult(response, '配置校验')
  } catch (error) {
    ElMessage.error('校验配置失败: ' + (error?.message || error?.detail || '未知错误'))
  }
}

const handleTest = async () => {
  try {
    await saveIfModified()
    const response = await configApi.testConfig()
    showTestResult(response, '配置测试')
  } catch (error) {
    ElMessage.error('测试配置失败: ' + (error?.message || error?.detail || '未知错误'))
  }
}

const handleApply = async () => {
  if (applying.value) return
  try {
    await saveIfModified()
    await ElMessageBox.confirm(
      '强制覆盖会将工作副本覆盖到实际 conf/ 配置目录，但不会重载 Nginx。建议覆盖后手动重启 Nginx 使配置生效。是否继续？',
      '强制覆盖确认',
      { confirmButtonText: '覆盖配置', cancelButtonText: '取消', type: 'warning' }
    )

    applying.value = true
    const response = await configApi.applyConfig()
    if (response.success) {
      await ElMessageBox.alert('配置目录已成功覆盖。\n\n建议重启 Nginx 使新配置生效。', '覆盖成功', {
        confirmButtonText: '知道了',
        type: 'success'
      })
      configInfo.value.pending_changes = false
      await loadConfig()
      await handleLoadBackups()
    } else {
      ElMessage.error('强制覆盖失败: ' + response.message)
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.detail || error?.message || '强制覆盖配置失败')
    }
  } finally {
    applying.value = false
  }
}

const handleReload = async () => {
  try {
    await saveIfModified()
    await ElMessageBox.confirm('确定要重新装载配置吗？', '提示', { type: 'warning' })
    const response = await configApi.reloadConfig()
    if (response.success) {
      const backupInfo = response.backup_id ? `，已创建备份 #${response.backup_id}` : ''
      ElMessage.success(`配置重载成功${backupInfo}`)
      configInfo.value.pending_changes = false
      isModified.value = false
      await loadConfig()
      await handleLoadBackups()
    } else {
      showTestResult(response.test_result || response, '配置重载')
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重新装载配置失败: ' + (error?.message || error?.detail || error))
    }
  }
}

const sanitizeFileName = (value) => {
  const cleaned = value.trim().toLowerCase().replace(/^\*\./, 'wildcard-').replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '')
  return cleaned || 'default'
}

const handleNewSite = async () => {
  try {
    const { value } = await ElMessageBox.prompt('请输入站点域名', '新建站点', {
      inputPattern: /.+/,
      inputErrorMessage: '域名不能为空',
      confirmButtonText: '创建',
      cancelButtonText: '取消'
    })
    const domain = value.trim()
    const path = `conf.d/${sanitizeFileName(domain)}.conf`
    const content = `server {\n    listen 80;\n    server_name ${domain};\n\n    root html;\n    index index.html index.htm;\n\n    location / {\n        try_files $uri $uri/ =404;\n    }\n}\n`
    await configApi.updateFile(path, content)
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    await openFile(path, { discardChanges: true })
    sidebarTab.value = 'sites'
    ElMessage.success('站点配置已创建')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.detail || error?.message || '创建站点失败')
    }
  }
}

const handleNewFile = async () => {
  try {
    const { value } = await ElMessageBox.prompt('请输入配置文件路径', '新建文件', {
      inputValue: 'conf.d/new-site.conf',
      inputPattern: /.+/,
      inputErrorMessage: '路径不能为空',
      confirmButtonText: '创建',
      cancelButtonText: '取消'
    })
    await configApi.updateFile(value.trim(), '')
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    await openFile(value.trim(), { discardChanges: true })
    ElMessage.success('配置文件已创建')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.detail || error?.message || '创建文件失败')
    }
  }
}

const handleNewDir = async () => {
  const parent = currentFilePath.value?.includes('/')
    ? currentFilePath.value.split('/').slice(0, -1).join('/')
    : ''
  try {
    const { value } = await ElMessageBox.prompt('请输入目录名称', '新建目录', {
      inputPattern: /^[^/\\]+$/,
      inputErrorMessage: '目录名不能为空，且不能包含 / 或 \\',
      confirmButtonText: '创建',
      cancelButtonText: '取消'
    })
    await configApi.createDirectory(parent, value.trim())
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    ElMessage.success('目录已创建')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.detail || error?.message || '创建目录失败')
    }
  }
}

const handleRename = async () => {
  if (!currentFilePath.value || currentFilePath.value === 'nginx.conf') return
  const oldName = currentFilePath.value.split('/').pop()
  try {
    const { value } = await ElMessageBox.prompt('请输入新名称', '重命名', {
      inputValue: oldName,
      inputPattern: /^[^/\\]+$/,
      inputErrorMessage: '名称不能为空，且不能包含 / 或 \\',
      confirmButtonText: '重命名',
      cancelButtonText: '取消'
    })
    const response = await configApi.renamePath(currentFilePath.value, value.trim())
    configInfo.value.pending_changes = true
    await loadTreeAndSites()
    await openFile(response.entry.path, { discardChanges: true })
    ElMessage.success('重命名成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.detail || error?.message || '重命名失败')
    }
  }
}

const handleDelete = async () => {
  if (!currentFilePath.value || currentFilePath.value === 'nginx.conf') return
  try {
    await ElMessageBox.confirm(`确定要删除 ${currentFilePath.value} 吗？`, '删除确认', { type: 'warning' })
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
    if (error !== 'cancel') {
      ElMessage.error(error?.detail || error?.message || '删除失败')
    }
  }
}

const handleSplitLegacy = async () => {
  try {
    await saveIfModified()
    await ElMessageBox.confirm(
      '拆分会在工作副本中保留 nginx.conf.legacy，并将 server 等配置拆到 conf.d。不会直接覆盖线上配置。',
      '拆分老配置',
      { type: 'warning', confirmButtonText: '开始拆分', cancelButtonText: '取消' }
    )
    const response = await configApi.splitLegacyConfig()
    await loadConfig()
    const message = response.test_result?.success
      ? `${response.message}，测试通过`
      : `${response.message || '拆分完成'}，请检查测试结果`
    ElMessage.success(message)
    if (response.test_result && !response.test_result.success) {
      showTestResult(response.test_result, '拆分后配置测试')
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.detail || error?.message || '拆分配置失败')
    }
  }
}

const handleMergedPreview = async () => {
  try {
    await saveIfModified()
    const response = await configApi.getMergedPreview()
    previewContent.value = response.content || ''
    previewVisible.value = true
    await nextTick()
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || '生成合并预览失败')
  }
}

const handleLoadBackups = async () => {
  backupLoading.value = true
  try {
    const res = await configApi.getBackups()
    const list = res?.backups || []
    backupOptions.value = list.map((item) => {
      const timeText = item.created_at ? formatDateTime(item.created_at) : '未知时间'
      const lastVersionTag = item.is_last_version ? ' [最后版本]' : ''
      return {
        id: item.id,
        label: `${timeText}（ID: ${item.id}）${lastVersionTag}`
      }
    })
    selectedBackupId.value = backupOptions.value[0]?.id || null
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || '获取备份列表失败')
  } finally {
    backupLoading.value = false
  }
}

const handleCreateBackup = async () => {
  backupLoading.value = true
  try {
    const res = await configApi.createBackup()
    if (res?.success) {
      ElMessage.success('备份创建成功（已保存当前线上配置目录）')
      await handleLoadBackups()
    } else {
      ElMessage.error(res?.message || '备份创建失败')
    }
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || '创建备份失败')
  } finally {
    backupLoading.value = false
  }
}

const handleRollback = async () => {
  if (!selectedBackupId.value) {
    ElMessage.warning('请先选择一个备份版本')
    return
  }
  try {
    await ElMessageBox.confirm('确定要将配置目录回滚到所选备份版本吗？回滚会覆盖当前工作副本。', '回滚确认', {
      type: 'warning'
    })
    backupLoading.value = true
    const res = await configApi.restoreBackup(selectedBackupId.value)
    if (res?.success) {
      ElMessage.success('配置已回滚到所选版本')
      await loadConfig()
      await handleLoadBackups()
    } else {
      ElMessage.error(res?.message || '回滚失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.detail || error?.message || '回滚失败')
    }
  } finally {
    backupLoading.value = false
  }
}
</script>

<style scoped>
.config-page {
  padding: 20px;
}

.card-header,
.header-actions,
.config-toolbar,
.backup-row,
.editor-header {
  display: flex;
  align-items: center;
}

.card-header {
  justify-content: space-between;
  gap: 16px;
}

.header-actions,
.config-toolbar,
.backup-row {
  gap: 8px;
  flex-wrap: wrap;
}

.config-info,
.config-toolbar {
  margin-bottom: 16px;
}

.backup-select {
  min-width: 320px;
}

.backup-btn {
  white-space: nowrap;
}

.config-path {
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.text-muted {
  color: var(--text-muted);
  font-style: italic;
}

.config-workspace {
  display: grid;
  grid-template-columns: minmax(260px, 320px) 1fr;
  gap: 16px;
  min-height: 680px;
}

.config-sidebar,
.editor-panel {
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
}

.config-sidebar {
  padding: 8px;
}

.site-item {
  padding: 10px 12px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid transparent;
}

.site-item:hover,
.site-item.active {
  border-color: var(--nginx-green);
  background: var(--nginx-green-light);
}

.site-name,
.site-path {
  display: block;
}

.site-name {
  font-weight: 600;
  color: var(--text-primary);
}

.site-path {
  margin-top: 4px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.config-tree {
  background: transparent;
}

.editor-panel {
  padding: 12px;
  min-width: 0;
}

.editor-header {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.current-file {
  margin-right: 8px;
  font-family: 'Courier New', monospace;
  font-weight: 600;
}

.working-copy-alert {
  margin-top: 16px;
}

.working-copy-text {
  margin: 6px 0 0;
}

.preview-content {
  max-height: 70vh;
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: #111827;
  color: #e5e7eb;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  white-space: pre-wrap;
}

@media (max-width: 900px) {
  .config-workspace {
    grid-template-columns: 1fr;
  }

  .card-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
