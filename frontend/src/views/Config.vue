<template>
  <div class="config-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Nginx 配置</span>
          <div>
            <el-button type="info" @click="handleFormat">
              <el-icon><MagicStick /></el-icon>
              <span class="btn-label">格式化</span>
            </el-button>
            <el-button type="cyan" @click="handleValidate">
              <el-icon><Finished /></el-icon>
              <span class="btn-label">校验配置</span>
            </el-button>
            <el-button type="purple" @click="handleTest">
              <el-icon><Cpu /></el-icon>
              <span class="btn-label">测试配置</span>
            </el-button>
            <el-button type="success" @click="handleSave" :loading="saving">
              <el-icon><DocumentChecked /></el-icon>
              <span class="btn-label">保存</span>
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
          <el-descriptions-item label="配置文件路径" :span="2">
            <el-text v-if="configInfo.config_path" class="config-path" size="small">
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
          <el-descriptions-item label="临时配置状态">
            <el-tag
              :type="configInfo.pending_changes ? 'warning' : 'success'"
              size="small"
            >
              {{ configInfo.pending_changes ? '存在未应用的修改' : '已与运行版本同步' }}
            </el-tag>
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
                <el-icon><RefreshRight /></el-icon>
                <span class="btn-label">刷新</span>
              </el-button>
              <el-button
                type="primary"
                class="backup-btn"
                @click="handleCreateBackup"
                :loading="backupLoading"
              >
                <el-icon><DocumentAdd /></el-icon>
                <span class="btn-label">手动备份</span>
              </el-button>
              <el-button
                type="warning"
                class="backup-btn"
                :disabled="!selectedBackupId"
                @click="handleRollback"
              >
                <el-icon><RefreshLeft /></el-icon>
                <span class="btn-label">回滚到所选版本</span>
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
      <el-alert
        class="working-copy-alert"
        type="info"
        show-icon
        :closable="false"
      >
        <template #title>临时副本模式</template>
        <p class="working-copy-text">
          保存后仅更新工作副本，需先测试/校验，再点击"重新装载"才能覆盖线上 nginx.conf 并自动备份。
        </p>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
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
  RefreshLeft
} from '@element-plus/icons-vue'

const configContent = ref('')
const isModified = ref(false)
const configInfo = ref({
  nginx_version: null,
  nginx_version_detail: null,
  config_path: null,
  active_version: null,
  install_path: null,
  binary: null,
  pending_changes: false
})

const backupOptions = ref([])
const selectedBackupId = ref(null)
const backupLoading = ref(false)
const saving = ref(false)

onMounted(async () => {
  await loadConfig()
  await handleLoadBackups()
  window.addEventListener('keydown', handleSaveShortcut)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleSaveShortcut)
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
      binary: response.binary || null,
      pending_changes: Boolean(response.pending_changes)
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

const handleFormat = async () => {
  // 保存原始内容作为备份
  const originalContent = configContent.value
  
  try {
    const response = await configApi.formatConfig(configContent.value)
    if (response.success && response.formatted) {
      // 确保格式化后的内容不为空
      if (response.formatted.trim()) {
        configContent.value = response.formatted
        isModified.value = true
        ElMessage.success('配置已格式化')
      } else {
        // 如果格式化后为空，保留原内容
        configContent.value = originalContent
        ElMessage.warning('格式化后内容为空，已保留原配置')
      }
    } else {
      // 格式化失败时，确保保留原内容
      if (response.formatted) {
        configContent.value = response.formatted
      } else {
        configContent.value = originalContent
      }
      ElMessage.warning(response.message || '格式化失败，已保留原配置')
    }
  } catch (error) {
    // 出错时恢复原内容
    configContent.value = originalContent
    ElMessage.error('格式化配置失败，已保留原配置')
  }
}

const handleValidate = async () => {
  try {
    const response = await configApi.validateConfig(configContent.value)
    if (response.success) {
      let message = '配置校验成功'
      if (response.warnings && response.warnings.length > 0) {
        message += `，但有 ${response.warnings.length} 个警告`
      }
      ElMessage.success(message)
      
      // 如果有警告或错误，显示详细信息
      if (response.errors && response.errors.length > 0) {
        ElMessageBox.alert(
          `发现 ${response.errors.length} 个错误：\n\n${response.errors.join('\n')}`,
          '配置校验错误',
          { type: 'error' }
        )
      } else if (response.warnings && response.warnings.length > 0) {
        ElMessageBox.alert(
          `发现 ${response.warnings.length} 个警告：\n\n${response.warnings.join('\n')}`,
          '配置校验警告',
          { type: 'warning' }
        )
      }
    } else {
      let errorMsg = response.message || '配置校验失败'
      if (response.errors && response.errors.length > 0) {
        errorMsg += '\n\n错误详情：\n' + response.errors.join('\n')
      }
      ElMessageBox.alert(errorMsg, '配置校验失败', { type: 'error' })
    }
  } catch (error) {
    ElMessage.error('校验配置失败')
  }
}

const handleTest = async () => {
  try {
    const response = await configApi.testConfig()
    if (response.success) {
      ElMessage.success('配置测试成功')
    } else {
      ElMessage.error('配置测试失败: ' + response.message)
      if (response.output) {
        ElMessageBox.alert(response.output, '测试输出', { type: 'error' })
      }
    }
  } catch (error) {
    ElMessage.error('测试配置失败')
  }
}

const handleSave = async () => {
  if (saving.value) return

  try {
    saving.value = true
    await configApi.updateConfig(configContent.value)
    ElMessage.success('配置已保存到临时副本')
    isModified.value = false
    configInfo.value.pending_changes = true
    await handleLoadBackups()
  } catch (error) {
    ElMessage.error('保存配置失败')
  } finally {
    saving.value = false
  }
}

const handleSaveShortcut = (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    if (!saving.value) {
      handleSave()
    }
  }
}

const handleReload = async () => {
  try {
    await ElMessageBox.confirm('确定要重新装载配置吗？', '提示', {
      type: 'warning'
    })
    
    const response = await configApi.reloadConfig()
    if (response.success) {
      const backupInfo = response.backup_id ? `，已创建备份 #${response.backup_id}` : ''
      ElMessage.success(`配置重载成功${backupInfo}`)
      configInfo.value.pending_changes = false
      await loadConfig()
    } else {
      ElMessage.error('配置重载失败: ' + response.message)
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重新装载配置失败')
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
        ? formatDateTime(item.created_at)
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
  color: var(--text-muted);
  font-style: italic;
}

.working-copy-alert {
  margin-top: 12px;
}

.working-copy-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
}
</style>

