<template>
  <div class="files-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>文件管理</span>
          <div class="card-actions">
            <el-select
              v-model="selectedDirectory"
              placeholder="选择 Nginx 目录/版本"
              style="width: 240px; margin-right: 8px"
              @change="handleDirectoryChange"
            >
              <el-option
                v-for="version in versions"
                :key="version.directory"
                :label="formatOptionLabel(version)"
                :value="version.directory"
              />
            </el-select>
            <el-switch
              v-model="rootOnly"
              active-text="整个目录"
              inactive-text="仅 HTML"
              style="margin-right: 8px"
              @change="handleRootOnlyChange"
            />
            <el-button size="small" type="info" @click="handleGoRoot">根目录</el-button>
            <el-button size="small" type="info" @click="handleGoParent" :disabled="!currentPath">上一级</el-button>
            <el-button size="small" type="primary" @click="handleUpload">上传文件</el-button>
            <el-button size="small" type="cyan" @click="handleCreateDir">新建文件夹</el-button>
            <el-button size="small" type="info" text @click="handleRefresh">刷新</el-button>
          </div>
        </div>
      </template>
      <div class="path-info" v-if="displayRootPath || currentPath">
        <div class="path-line">
          <span class="path-label">根路径：</span>
          <span class="path-value">{{ displayRootPath || '-' }}</span>
        </div>
        <div class="path-line">
          <span class="path-label">相对路径：</span>
          <span class="path-value">/{{ currentPath || '' }}</span>
        </div>
      </div>
      <div class="version-info" v-if="selectedDirectory">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="当前 Nginx 目录">
            <el-text type="info" size="small">{{ selectedDirectory || '-' }}</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="当前 Nginx 版本">
            <el-tag v-if="formatVersionLabel(currentVersionInfo)" type="info" size="small">
              {{ formatVersionLabel(currentVersionInfo) }}
            </el-tag>
            <span v-else class="text-muted">未知</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="currentVersionInfo?.running" label="运行状态" :span="2">
            <el-tag type="success" size="small">运行中</el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <el-table
        :data="fileList"
        style="width: 100%"
        :loading="loading"
        border
        table-layout="auto"
        :row-key="getRowKey"
        empty-text="暂无文件，请先选择目录或上传文件"
      >
        <el-table-column prop="name" label="文件名" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span
              class="file-name"
              :class="{ 'is-dir': row.is_dir }"
              @dblclick="handleRowDblClick(row)"
            >
              <el-icon v-if="row.is_dir" class="file-icon">
                <folder />
              </el-icon>
              <el-icon v-else class="file-icon">
                <document />
              </el-icon>
              <span class="file-name-text">{{ row.name }}</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="140" align="center">
          <template #default="{ row }">
            <span v-if="!row.is_dir">{{ formatSize(row.size) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="修改时间" width="200" align="center" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.modified_time || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right" align="center" class-name="file-ops-column">
          <template #default="{ row }">
            <div class="file-actions" :class="{ 'is-dir': row.is_dir }">
              <template v-if="row.is_dir">
                <el-tooltip content="进入" placement="top">
                  <el-button
                    size="small"
                    type="success"
                    circle
                    aria-label="进入目录"
                    @click="enterDirectory(row)"
                  >
                    <el-icon><ArrowRightBold /></el-icon>
                  </el-button>
                </el-tooltip>
              </template>
              <template v-else>
                <el-tooltip content="编辑" placement="top">
                  <el-button
                    size="small"
                    type="info"
                    circle
                    aria-label="编辑文件"
                    @click="handleEdit(row)"
                  >
                    <el-icon><Edit /></el-icon>
                  </el-button>
                </el-tooltip>
                <el-tooltip content="下载" placement="top">
                  <el-button
                    size="small"
                    type="cyan"
                    circle
                    aria-label="下载文件"
                    @click="handleDownload(row)"
                  >
                    <el-icon><Download /></el-icon>
                  </el-button>
                </el-tooltip>
              </template>
              <el-tooltip content="重命名" placement="top">
                <el-button
                  size="small"
                  type="warning"
                  circle
                  aria-label="重命名"
                  @click="handleRename(row)"
                >
                  <el-icon><EditPen /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button
                  size="small"
                  type="danger"
                  circle
                  aria-label="删除"
                  @click="handleDelete(row)"
                >
                  <el-icon><DeleteIcon /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 隐藏的上传输入框 -->
      <input
        ref="uploadInput"
        type="file"
        multiple
        style="display: none"
        @change="handleFileChange"
      />

      <!-- 文件编辑对话框（MonacoEditor） -->
      <el-dialog 
        v-model="editDialogVisible" 
        title="编辑文件" 
        width="80%"
        :close-on-click-modal="false"
      >
        <div class="edit-file-path">路径：/{{ editForm.path }}</div>
        <MonacoEditor
          v-model="editForm.content"
          :language="editLanguage"
          height="600px"
        />
        <template #footer>
          <span class="dialog-footer">
            <el-button @click="editDialogVisible = false">取 消</el-button>
            <el-button type="primary" @click="submitEdit">保 存</el-button>
          </span>
        </template>
      </el-dialog>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { filesApi } from '../api/files'
import { nginxApi } from '../api/nginx'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Folder, Document, ArrowRightBold, Edit, Download, EditPen, Delete as DeleteIcon } from '@element-plus/icons-vue'
import MonacoEditor from '../components/MonacoEditor.vue'

const fileList = ref([])
const currentPath = ref('')
const loading = ref(false)
const uploadInput = ref(null)
const versions = ref([])
const selectedDirectory = ref(null)
const rootOnly = ref(false)

const editDialogVisible = ref(false)
const editForm = ref({
  path: '',
  content: ''
})
const editLanguage = ref('plaintext')

const currentVersionInfo = computed(() => {
  return versions.value.find(v => v.directory === selectedDirectory.value)
})

const formatVersionLabel = (info) => {
  if (!info || typeof info !== 'object') return '未知'
  return info.version || '未知'
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

const getRowKey = (row) => row.path || row.name
const rootBasePath = ref('')

const displayRootPath = computed(() => {
  return (rootBasePath.value || '').replace(/\/+$/, '')
})


const loadVersions = async () => {
  try {
    const data = await nginxApi.listVersions()
    versions.value = data || []
    if (versions.value.length === 0) {
      selectedDirectory.value = null
      return
    }

    // 若当前选择仍然存在，则保留
    if (selectedDirectory.value) {
      const stillExists = versions.value.some(v => v.directory === selectedDirectory.value)
      if (stillExists) {
        return
      }
    }

    // 默认优先运行中目录，其次任一已编译，否则第一个
    const running = versions.value.find(v => v.running)
    if (running) {
      selectedDirectory.value = running.directory
      return
    }

    const compiled = versions.value.find(v => v.compiled)
    if (compiled) {
      selectedDirectory.value = compiled.directory
      return
    }

    selectedDirectory.value = versions.value[0].directory
  } catch (error) {
    console.error('加载版本列表失败:', error)
  }
}

const handleDirectoryChange = () => {
  currentPath.value = ''
  loadFiles()
}

const handleRootOnlyChange = () => {
  currentPath.value = ''
  loadFiles()
}

const loadFiles = async () => {
  if (!selectedDirectory.value) {
    return
  }
  try {
    loading.value = true
    rootBasePath.value = ''
    const response = await filesApi.listFiles(currentPath.value || undefined, selectedDirectory.value, rootOnly.value)
    fileList.value = response.files || []
    rootBasePath.value = response.root_path || ''
  } catch (error) {
    ElMessage.error(error.detail || '加载文件列表失败')
  } finally {
    loading.value = false
  }
}

const handleUpload = () => {
  if (uploadInput.value) {
    uploadInput.value.value = ''
    uploadInput.value.click()
  }
}

const handleFileChange = async (event) => {
  const files = Array.from(event.target.files || [])
  if (!files.length) return
  if (!selectedDirectory.value) {
    ElMessage.warning('请先选择 Nginx 目录/版本')
    return
  }
  try {
    const res = await filesApi.uploadFile(
      currentPath.value || undefined,
      files,
      selectedDirectory.value,
      rootOnly.value
    )
    ElMessage.success(res.message || '上传成功')
    loadFiles()
  } catch (error) {
    ElMessage.error(error.detail || '上传失败')
  } finally {
    if (uploadInput.value) {
      uploadInput.value.value = ''
    }
  }
}

const handleCreateDir = async () => {
  if (!selectedDirectory.value) {
    ElMessage.warning('请先选择 Nginx 目录/版本')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt('请输入新建文件夹名称', '新建文件夹', {
      inputPattern: /^[^/\\]+$/,
      inputErrorMessage: '文件夹名称不能为空，且不能包含 / 或 \\',
      confirmButtonText: '确 定',
      cancelButtonText: '取 消'
    })
    await filesApi.createDirectory(
      currentPath.value || undefined,
      value,
      selectedDirectory.value,
      rootOnly.value
    )
    ElMessage.success('创建文件夹成功')
    loadFiles()
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error.detail || '创建文件夹失败')
  }
}

const handleRefresh = () => {
  loadFiles()
}

const handleEdit = async (file) => {
  if (file.is_dir) {
    enterDirectory(file)
    return
  }
  if (!selectedDirectory.value) {
    ElMessage.warning('请先选择 Nginx 目录/版本')
    return
  }
  try {
    const res = await filesApi.getFile(file.path, selectedDirectory.value, rootOnly.value)
    editForm.value.path = res.path
    editForm.value.content = res.content
    editLanguage.value = detectLanguageByFilename(file.name)
    editDialogVisible.value = true
  } catch (error) {
    ElMessage.error(error.detail || '读取文件失败')
  }
}

const submitEdit = async () => {
  if (!selectedDirectory.value) {
    ElMessage.warning('请先选择 Nginx 目录/版本')
    return
  }
  try {
    await filesApi.updateFile(
      editForm.value.path,
      editForm.value.content,
      selectedDirectory.value,
      rootOnly.value
    )
    ElMessage.success('保存成功')
    editDialogVisible.value = false
    loadFiles()
  } catch (error) {
    ElMessage.error(error.detail || '保存失败')
  }
}

const handleDelete = async (file) => {
  if (!selectedDirectory.value) {
    ElMessage.warning('请先选择 Nginx 目录/版本')
    return
  }
  try {
    await ElMessageBox.confirm('确定要删除吗？', '提示', { type: 'warning' })
    await filesApi.deleteFile(file.path, selectedDirectory.value, rootOnly.value)
    ElMessage.success('删除成功')
    loadFiles()
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error.detail || '删除失败')
  }
}

const handleRename = async (file) => {
  if (!selectedDirectory.value) {
    ElMessage.warning('请先选择 Nginx 目录/版本')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt('请输入新的名称', '重命名', {
      inputValue: file.name,
      inputPattern: /^[^/\\]+$/,
      inputErrorMessage: '名称不能为空，且不能包含 / 或 \\',
      confirmButtonText: '确 定',
      cancelButtonText: '取 消'
    })
    await filesApi.renameFile(file.path, value, selectedDirectory.value, rootOnly.value)
    ElMessage.success('重命名成功')
    loadFiles()
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error.detail || '重命名失败')
  }
}

const handleDownload = async (file) => {
  if (file.is_dir) {
    ElMessage.warning('暂不支持下载文件夹')
    return
  }
  if (!selectedDirectory.value) {
    ElMessage.warning('请先选择 Nginx 目录/版本')
    return
  }
  try {
    const blob = await filesApi.downloadFile(file.path, selectedDirectory.value, rootOnly.value)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = file.name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(error.detail || '下载失败')
  }
}

const enterDirectory = (file) => {
  if (!file.is_dir) return
  currentPath.value = file.path
  loadFiles()
}

const handleRowDblClick = (row) => {
  if (row.is_dir) {
    enterDirectory(row)
  }
}

const handleGoRoot = () => {
  currentPath.value = ''
  loadFiles()
}

const handleGoParent = () => {
  if (!currentPath.value) return
  const parts = currentPath.value.split('/').filter(Boolean)
  parts.pop()
  currentPath.value = parts.join('/')
  loadFiles()
}

const formatSize = (size) => {
  if (!size || size <= 0) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let idx = 0
  let value = size
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx++
  }
  return `${value.toFixed(1)} ${units[idx]}`
}

// 根据文件名简单推断语言，供 MonacoEditor 高亮使用
const detectLanguageByFilename = (filename) => {
  const lower = (filename || '').toLowerCase()
  if (lower.endsWith('.conf')) return 'nginx'
  if (lower.endsWith('.js')) return 'javascript'
  if (lower.endsWith('.ts')) return 'typescript'
  if (lower.endsWith('.json')) return 'json'
  if (lower.endsWith('.html') || lower.endsWith('.htm')) return 'html'
  if (lower.endsWith('.css') || lower.endsWith('.scss') || lower.endsWith('.less')) return 'css'
  if (lower.endsWith('.yml') || lower.endsWith('.yaml')) return 'yaml'
  if (lower.endsWith('.py')) return 'python'
  if (lower.endsWith('.sh')) return 'shell'
  return 'plaintext'
}

onMounted(async () => {
  await loadVersions()
  if (selectedDirectory.value) {
    loadFiles()
  }
})
</script>

<style scoped>
.files-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.path-info {
  margin: 12px 0;
  padding: 12px;
  background-color: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.path-line {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  line-height: 1.5;
}

.path-label {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.path-value {
  color: var(--text-primary);
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  word-break: break-all;
  flex: 1;
}

.file-name {
  cursor: default;
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  gap: 6px;
}

.file-name.is-dir {
  cursor: pointer;
  color: var(--nginx-green);
}

.file-name-text {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-icon {
  flex-shrink: 0;
}

.file-actions {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}

.file-ops-column .cell {
  padding-right: 12px;
}

.edit-file-path {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.version-info {
  margin-bottom: 16px;
}

.running-badge {
  margin-left: 8px;
  font-size: 12px;
  color: var(--nginx-green);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  width: 100%;
}
</style>

