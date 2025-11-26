<template>
  <div class="config-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Nginx 配置</span>
          <div>
            <el-button @click="handleTest">测试配置</el-button>
            <el-button type="success" @click="handleSave">保存</el-button>
            <el-button type="warning" @click="handleReload">重载配置</el-button>
          </div>
        </div>
      </template>
      <div class="config-info">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="当前 Nginx 版本">
            <el-tag v-if="configInfo.nginx_version" type="info">
              {{ configInfo.nginx_version }}
            </el-tag>
            <span v-else class="text-muted">未知</span>
          </el-descriptions-item>
          <el-descriptions-item label="配置文件路径">
            <el-text v-if="configInfo.config_path" class="config-path">
              {{ configInfo.config_path }}
            </el-text>
            <span v-else class="text-muted">未知</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="configInfo.nginx_version_detail" label="版本详情" :span="2">
            <el-text type="info" size="small">{{ configInfo.nginx_version_detail }}</el-text>
          </el-descriptions-item>
          <el-descriptions-item v-if="configInfo.binary" label="可执行文件路径" :span="2">
            <el-text type="info" size="small">{{ configInfo.binary }}</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="配置备份版本" :span="2">
            <div class="backup-row">
              <el-select
                v-model="selectedBackupId"
                placeholder="选择一个备份版本（最多显示最近 10 个）"
                style="min-width: 320px"
                :disabled="backupLoading || backupOptions.length === 0"
              >
                <el-option
                  v-for="item in backupOptions"
                  :key="item.id"
                  :label="item.label"
                  :value="item.id"
                />
              </el-select>
              <el-button
                class="backup-btn"
                @click="handleLoadBackups"
                :loading="backupLoading"
                link
              >
                刷新
              </el-button>
              <el-button
                type="primary"
                class="backup-btn"
                @click="handleCreateBackup"
                :loading="backupLoading"
              >
                手动备份
              </el-button>
              <el-button
                type="warning"
                class="backup-btn"
                :disabled="!selectedBackupId"
                @click="handleRollback"
              >
                回滚到所选版本
              </el-button>
            </div>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <MonacoEditor
        v-model="configContent"
        language="nginx"
        height="600px"
        @change="handleContentChange"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { configApi } from '../api/config'
import MonacoEditor from '../components/MonacoEditor.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const configContent = ref('')
const isModified = ref(false)
const configInfo = ref({
  nginx_version: null,
  nginx_version_detail: null,
  config_path: null,
  active_version: null,
  install_path: null,
  binary: null
})

const backupOptions = ref([])
const selectedBackupId = ref(null)
const backupLoading = ref(false)

onMounted(async () => {
  await loadConfig()
  await handleLoadBackups()
})

const loadConfig = async () => {
  try {
    const response = await configApi.getConfig()
    configContent.value = response.content || ''
    configInfo.value = {
      nginx_version: response.nginx_version || null,
      nginx_version_detail: response.nginx_version_detail || null,
      config_path: response.config_path || null,
      active_version: response.active_version || null,
      install_path: response.install_path || null,
      binary: response.binary || null
    }
    isModified.value = false
  } catch (error) {
    console.error('加载配置失败:', error)
    ElMessage.error(error?.detail || error?.message || '加载配置失败')
  }
}

const handleContentChange = () => {
  isModified.value = true
}

const handleTest = async () => {
  try {
    const response = await configApi.testConfig()
    if (response.success) {
      ElMessage.success('配置测试成功')
    } else {
      ElMessage.error('配置测试失败: ' + response.message)
    }
  } catch (error) {
    ElMessage.error('测试配置失败')
  }
}

const handleSave = async () => {
  try {
    await configApi.updateConfig(configContent.value)
    ElMessage.success('配置已保存')
    isModified.value = false
    // 保存时会自动创建备份，这里刷新一下备份列表
    await handleLoadBackups()
  } catch (error) {
    ElMessage.error('保存配置失败')
  }
}

const handleReload = async () => {
  try {
    await ElMessageBox.confirm('确定要重载配置吗？', '提示', {
      type: 'warning'
    })
    
    const response = await configApi.reloadConfig()
    if (response.success) {
      ElMessage.success('配置重载成功')
    } else {
      ElMessage.error('配置重载失败: ' + response.message)
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重载配置失败')
    }
  }
}

const handleLoadBackups = async () => {
  backupLoading.value = true
  try {
    const res = await configApi.getBackups()
    const list = res?.backups || []
    backupOptions.value = list.map((item) => {
      const timeText = item.created_at
        ? new Date(item.created_at).toLocaleString()
        : '未知时间'
      return {
        id: item.id,
        label: `${timeText}（ID: ${item.id}）`
      }
    })
    // 默认选择最新的一条
    if (backupOptions.value.length > 0) {
      selectedBackupId.value = backupOptions.value[0].id
    } else {
      selectedBackupId.value = null
    }
  } catch (error) {
    console.error('获取备份列表失败:', error)
    ElMessage.error(error?.detail || error?.message || '获取备份列表失败')
  } finally {
    backupLoading.value = false
  }
}

const handleCreateBackup = async () => {
  try {
    backupLoading.value = true
    const res = await configApi.createBackup()
    if (res?.success) {
      ElMessage.success('备份创建成功')
      await handleLoadBackups()
    } else {
      ElMessage.error(res?.message || '备份创建失败')
    }
  } catch (error) {
    console.error('创建备份失败:', error)
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
    await ElMessageBox.confirm(
      '确定要将当前配置回滚到所选备份版本吗？此操作会覆盖当前配置文件。',
      '回滚确认',
      {
        type: 'warning'
      }
    )
  } catch {
    return
  }

  try {
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
    console.error('回滚失败:', error)
    ElMessage.error(error?.detail || error?.message || '回滚失败')
  } finally {
    backupLoading.value = false
  }
}
</script>

<style scoped>
.config-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.config-info {
  margin-bottom: 20px;
}

.backup-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.backup-btn {
  white-space: nowrap;
}

.config-path {
  font-family: 'Courier New', monospace;
  font-size: 12px;
}

.text-muted {
  color: #909399;
  font-style: italic;
}
</style>

