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
            <el-button type="primary" @click="uploadDialogVisible = true">
              上传源码包
            </el-button>
            <el-button type="primary" link @click="loadVersions">刷新</el-button>
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
                type="primary"
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
                type="danger"
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
    >
      <el-form :model="downloadForm" label-width="100px">
        <el-form-item label="版本号">
          <el-select
            v-model="downloadForm.version"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入版本号，例如：1.28.0"
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
            placeholder="留空使用官方地址：https://nginx.org/download/nginx-&lt;version&gt;.tar.gz"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="downloadDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="downloadLoading" @click="handleDownload">
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
          <el-button @click="uploadDialogVisible = false">取消</el-button>
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
import { ref, onMounted } from 'vue'
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

const handleDownload = async () => {
  if (!downloadForm.value.version) {
    ElMessage.warning('请先输入版本号')
    return
  }
  const targetVersion = downloadForm.value.version
  downloadLoading.value = true
  setBuilding(targetVersion, true)
  try {
    await nginxApi.downloadAndBuild({
      version: targetVersion,
      url: downloadForm.value.url || undefined
    })
    ElMessage.success('下载并编译任务完成')
    await loadVersions()
    downloadDialogVisible.value = false
  } catch (error) {
    // 有些情况下后端实际上已经在后台继续下载/编译，但前端因为超时/代理中断收到了错误
    // 这里在报错前先刷新一次列表，如果目标版本已经出现，则提示“可能已完成”
    await loadVersions()
    const exists = versions.value?.some((v) => v.version === targetVersion)
    if (exists) {
      ElMessage.success('下载/编译任务可能已在后台完成，请查看版本列表')
      downloadDialogVisible.value = false
    } else {
      ElMessage.error(error.detail || '下载编译失败')
    }
  } finally {
    downloadLoading.value = false
    setBuilding(targetVersion, false)
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
  color: #909399;
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
</style>


