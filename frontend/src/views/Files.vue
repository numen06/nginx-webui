<template>
  <div class="files-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>文件管理</span>
          <div class="card-actions">
            <el-select
              v-model="selectedVersion"
              placeholder="选择 Nginx 版本"
              style="width: 200px; margin-right: 8px"
              @change="handleVersionChange"
            >
              <el-option
                v-for="version in versions"
                :key="version.version"
                :label="`${version.version}${version.running ? ' (运行中)' : ''}`"
                :value="version.version"
              />
            </el-select>
            <el-switch
              v-model="rootOnly"
              active-text="整个目录"
              inactive-text="仅 HTML"
              style="margin-right: 8px"
              @change="handleRootOnlyChange"
            />
            <span class="current-path">当前路径：/{{ currentPath || '' }}</span>
            <el-button size="small" @click="handleGoRoot">根目录</el-button>
            <el-button size="small" @click="handleGoParent" :disabled="!currentPath">上一级</el-button>
            <el-button size="small" @click="handleUpload">上传文件</el-button>
            <el-button size="small" @click="handleCreateDir">新建文件夹</el-button>
            <el-button size="small" @click="handleRefresh">刷新</el-button>
          </div>
        </div>
      </template>
      <div class="version-info" v-if="selectedVersion">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="当前 Nginx 版本">
            <el-tag :type="currentVersionInfo?.running ? 'success' : 'info'">
              {{ selectedVersion }}
            </el-tag>
            <span v-if="currentVersionInfo?.running" class="running-badge">运行中</span>
          </el-descriptions-item>
          <el-descriptions-item label="安装路径">
            <el-text type="info" size="small">{{ currentVersionInfo?.install_path || '-' }}</el-text>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <el-table :data="fileList" style="width: 100%" :loading="loading">
        <el-table-column prop="name" label="文件名">
          <template #default="scope">
            <span
              class="file-name"
              :class="{ 'is-dir': scope.row.is_dir }"
              @dblclick="handleRowDblClick(scope.row)"
            >
              <el-icon v-if="scope.row.is_dir" class="file-icon">
                <folder />
              </el-icon>
              <el-icon v-else class="file-icon">
                <document />
              </el-icon>
              {{ scope.row.name }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="size" label="大小" width="120">
          <template #default="scope">
            <span v-if="!scope.row.is_dir">{{ formatSize(scope.row.size) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="modified_time" label="修改时间" width="180" />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="scope">
            <template v-if="scope.row.is_dir">
              <el-button size="small" @click="enterDirectory(scope.row)">进入</el-button>
            </template>
            <template v-else>
              <el-button size="small" @click="handleEdit(scope.row)">编辑</el-button>
              <el-button size="small" @click="handleDownload(scope.row)">下载</el-button>
            </template>
            <el-button size="small" @click="handleRename(scope.row)">重命名</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
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
      <el-dialog v-model="editDialogVisible" title="编辑文件" width="80%">
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
import { Folder, Document } from '@element-plus/icons-vue'
import MonacoEditor from '../components/MonacoEditor.vue'

const fileList = ref([])
const currentPath = ref('')
const loading = ref(false)
const uploadInput = ref(null)
const versions = ref([])
const selectedVersion = ref(null)
const rootOnly = ref(false)

const editDialogVisible = ref(false)
const editForm = ref({
  path: '',
  content: ''
})
const editLanguage = ref('plaintext')

const currentVersionInfo = computed(() => {
  return versions.value.find(v => v.version === selectedVersion.value)
})

const loadVersions = async () => {
  try {
    const data = await nginxApi.listVersions()
    versions.value = data || []
    // 默认选择运行中的版本，如果没有则选择第一个已编译的版本
    if (versions.value.length > 0) {
      const running = versions.value.find(v => v.running && v.compiled)
      if (running) {
        selectedVersion.value = running.version
      } else {
        const compiled = versions.value.find(v => v.compiled)
        if (compiled) {
          selectedVersion.value = compiled.version
        } else {
          selectedVersion.value = versions.value[0].version
        }
      }
    }
  } catch (error) {
    console.error('加载版本列表失败:', error)
  }
}

const handleVersionChange = () => {
  currentPath.value = ''
  loadFiles()
}

const handleRootOnlyChange = () => {
  currentPath.value = ''
  loadFiles()
}

const loadFiles = async () => {
  if (!selectedVersion.value) {
    return
  }
  try {
    loading.value = true
    const response = await filesApi.listFiles(currentPath.value || undefined, selectedVersion.value, rootOnly.value)
    fileList.value = response.files || []
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
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择 Nginx 版本')
    return
  }
  try {
    const res = await filesApi.uploadFile(currentPath.value || undefined, files, selectedVersion.value)
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
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择 Nginx 版本')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt('请输入新建文件夹名称', '新建文件夹', {
      inputPattern: /^[^/\\]+$/,
      inputErrorMessage: '文件夹名称不能为空，且不能包含 / 或 \\',
      confirmButtonText: '确 定',
      cancelButtonText: '取 消'
    })
    await filesApi.createDirectory(currentPath.value || undefined, value, selectedVersion.value)
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
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择 Nginx 版本')
    return
  }
  try {
    const res = await filesApi.getFile(file.path, selectedVersion.value)
    editForm.value.path = res.path
    editForm.value.content = res.content
    editLanguage.value = detectLanguageByFilename(file.name)
    editDialogVisible.value = true
  } catch (error) {
    ElMessage.error(error.detail || '读取文件失败')
  }
}

const submitEdit = async () => {
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择 Nginx 版本')
    return
  }
  try {
    await filesApi.updateFile(editForm.value.path, editForm.value.content, selectedVersion.value)
    ElMessage.success('保存成功')
    editDialogVisible.value = false
    loadFiles()
  } catch (error) {
    ElMessage.error(error.detail || '保存失败')
  }
}

const handleDelete = async (file) => {
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择 Nginx 版本')
    return
  }
  try {
    await ElMessageBox.confirm('确定要删除吗？', '提示', { type: 'warning' })
    await filesApi.deleteFile(file.path, selectedVersion.value)
    ElMessage.success('删除成功')
    loadFiles()
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error.detail || '删除失败')
  }
}

const handleRename = async (file) => {
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择 Nginx 版本')
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
    await filesApi.renameFile(file.path, value, selectedVersion.value)
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
  if (!selectedVersion.value) {
    ElMessage.warning('请先选择 Nginx 版本')
    return
  }
  try {
    const blob = await filesApi.downloadFile(file.path, selectedVersion.value)
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
  if (selectedVersion.value) {
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

.current-path {
  font-size: 13px;
  color: var(--text-secondary);
  margin-right: 8px;
}

.file-name {
  cursor: default;
  display: inline-flex;
  align-items: center;
}

.file-name.is-dir {
  cursor: pointer;
  color: var(--nginx-green);
}

.file-icon {
  margin-right: 4px;
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
</style>

