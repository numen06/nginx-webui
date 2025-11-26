<template>
  <div class="nginx-manager">
    <el-row :gutter="20">
      <el-col :span="10">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>在线下载并编译 Nginx</span>
            </div>
          </template>
          <el-form :model="downloadForm" label-width="100px">
            <el-form-item label="版本号">
              <el-input v-model="downloadForm.version" placeholder="例如：1.28.0" />
            </el-form-item>
            <el-form-item label="下载地址">
              <el-input
                v-model="downloadForm.url"
                placeholder="留空使用官方地址：https://nginx.org/download/nginx-&lt;version&gt;.tar.gz"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="downloadLoading" @click="handleDownload">
                下载并编译
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card style="margin-top: 20px">
          <template #header>
            <div class="card-header">
              <span>上传源码包并编译</span>
            </div>
          </template>
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
            <el-form-item>
              <el-button
                type="primary"
                :loading="uploading"
                :disabled="!selectedFile"
                @click="handleUpload"
              >
                上传并编译
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>Nginx 版本列表</span>
              <el-button type="primary" link @click="loadVersions">刷新</el-button>
            </div>
          </template>
          <el-table :data="versions" style="width: 100%">
            <el-table-column prop="version" label="版本" width="120" />
            <el-table-column prop="install_path" label="安装路径" min-width="220" />
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="row.running ? 'success' : 'info'">
                  {{ row.running ? '运行中' : '已停止' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="pid" label="PID" width="100">
              <template #default="{ row }">
                {{ row.pid || '-' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="220">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="success"
                  :disabled="row.running"
                  @click="startVersion(row.version)"
                >
                  启动
                </el-button>
                <el-button
                  size="small"
                  type="warning"
                  :disabled="!row.running"
                  @click="stopVersion(row.version)"
                >
                  停止
                </el-button>
                <el-button size="small" link @click="showBuildLog(row.version)">
                  编译日志
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-drawer
          v-model="logDrawerVisible"
          title="编译日志"
          size="50%"
          destroy-on-close
        >
          <div class="log-header">
            <span>版本：{{ currentLogVersion }}</span>
            <el-button type="primary" link @click="reloadBuildLog">刷新</el-button>
          </div>
          <el-scrollbar class="log-content">
            <pre>{{ buildLogContent || '暂无日志' }}</pre>
          </el-scrollbar>
        </el-drawer>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { nginxApi } from '../api/nginx'

const versions = ref([])
const downloadForm = ref({
  version: '',
  url: ''
})
const downloadLoading = ref(false)

const uploadRef = ref(null)
const selectedFile = ref(null)
const uploadVersion = ref('')
const uploading = ref(false)

const logDrawerVisible = ref(false)
const currentLogVersion = ref('')
const buildLogContent = ref('')

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
  downloadLoading.value = true
  try {
    await nginxApi.downloadAndBuild({
      version: downloadForm.value.version,
      url: downloadForm.value.url || undefined
    })
    ElMessage.success('下载并编译任务完成')
    await loadVersions()
  } catch (error) {
    ElMessage.error(error.detail || '下载编译失败')
  } finally {
    downloadLoading.value = false
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

const showBuildLog = async (version) => {
  currentLogVersion.value = version
  logDrawerVisible.value = true
  await reloadBuildLog()
}

const reloadBuildLog = async () => {
  if (!currentLogVersion.value) return
  try {
    const data = await nginxApi.getBuildLog(currentLogVersion.value)
    buildLogContent.value = data?.content || ''
  } catch (error) {
    ElMessage.error(error.detail || '获取编译日志失败')
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

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.log-content {
  height: 60vh;
  background-color: #1e1e1e;
  color: #f5f5f5;
  padding: 10px;
  border-radius: 4px;
}

.log-content pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-family: Menlo, Monaco, Consolas, 'Courier New', monospace;
  font-size: 12px;
  margin: 0;
}
</style>


