<template>
  <div class="git-sync-page">
    <el-card v-loading="gitLoading">
      <template #header>
        <div class="card-header">
          <div>
            <span>Git 配置同步</span>
            <p class="card-subtitle">配置仓库信息并将当前 nginx.conf 推送到远端</p>
          </div>
          <div>
            <el-button type="primary" @click="handleSaveGitConfig" :loading="gitSaving">
              <el-icon><DocumentChecked /></el-icon>
              <span class="btn-label">保存配置</span>
            </el-button>
            <el-button
              type="success"
              @click="handleSyncGit"
              :loading="gitSyncing"
              :disabled="!canSyncGit"
            >
              <el-icon><Refresh /></el-icon>
              <span class="btn-label">立即同步</span>
            </el-button>
          </div>
        </div>
      </template>

      <el-form label-width="120px" class="git-form">
        <el-form-item label="项目名称">
          <el-input
            v-model="gitConfig.project_name"
            placeholder="用于区分 data/git/<项目名称>/"
            clearable
          />
          <p class="help-text">
            默认建议：{{ defaultProjectName || '（无）' }}；同步目录 data/git/{{ resolvedProjectName }}
          </p>
        </el-form-item>
        <el-form-item label="仓库地址">
          <el-input
            v-model="gitConfig.repo_url"
            placeholder="请输入 Git 仓库地址（HTTPS）"
            clearable
          />
        </el-form-item>
        <el-form-item label="分支">
          <el-input v-model="gitConfig.branch" placeholder="默认为 main" clearable />
        </el-form-item>
        <el-form-item label="账号">
          <el-input v-model="gitConfig.username" placeholder="Git 账号" clearable />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            type="password"
            v-model="gitPassword"
            :placeholder="passwordPlaceholder"
            show-password
            clearable
            @input="handlePasswordInput"
          />
        </el-form-item>
      </el-form>

      <el-alert
        v-if="gitStatus.status || gitStatus.message"
        :type="syncStatusType"
        show-icon
        class="git-alert"
      >
        <p class="git-status">{{ syncStatusText }}</p>
        <p v-if="gitStatus.message" class="git-status-detail">{{ gitStatus.message }}</p>
      </el-alert>
      <p v-else class="git-status git-status-muted">尚未同步过 Git 仓库</p>

      <el-divider />
      <el-alert type="info" show-icon>
        <ul class="tips">
          <li>同步时将当前活跃版本的 nginx.conf 导出至 Git 仓库。</li>
          <li>凭据仅存储于后端数据库，加密传输，不会回显。</li>
          <li>仓库会被克隆到服务器 <code>data/git/{{ resolvedProjectName }}</code> 目录。</li>
        </ul>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { gitApi } from '../api/git'
import { ElMessage } from 'element-plus'

const gitConfig = ref({
  project_name: '',
  repo_url: '',
  username: '',
  branch: 'main',
  has_password: false
})
const gitPassword = ref('')
const passwordTouched = ref(false)
const defaultProjectName = ref('')
const gitStatus = ref({
  status: null,
  message: '',
  time: null
})
const gitLoading = ref(false)
const gitSaving = ref(false)
const gitSyncing = ref(false)

const passwordPlaceholder = computed(() => {
  if (gitConfig.value.has_password && !passwordTouched.value) {
    return '已保存，留空表示不修改'
  }
  return '请输入 Git 密码'
})

const canSyncGit = computed(() => {
  const hasRepo = Boolean(gitConfig.value.repo_url)
  const hasUser = Boolean(gitConfig.value.username)
  const hasPwd =
    gitConfig.value.has_password || (passwordTouched.value && gitPassword.value !== '')
  return hasRepo && hasUser && hasPwd
})

const syncStatusType = computed(() => {
  switch (gitStatus.value.status) {
    case 'success':
      return 'success'
    case 'failed':
      return 'error'
    case 'skipped':
      return 'info'
    default:
      return 'info'
  }
})

const resolvedProjectName = computed(
  () => gitConfig.value.project_name || defaultProjectName.value || '项目'
)

const syncStatusText = computed(() => {
  if (!gitStatus.value.status && !gitStatus.value.message) {
    return '尚未同步过 Git 仓库'
  }
  const timeText = gitStatus.value.time
    ? new Date(gitStatus.value.time).toLocaleString()
    : '未知时间'
  const statusMap = {
    success: '最近一次同步成功',
    failed: '最近一次同步失败',
    skipped: '最近一次同步无变更'
  }
  return `${statusMap[gitStatus.value.status] || '最近一次同步'}（${timeText}）`
})

onMounted(async () => {
  await loadGitConfig()
})

const loadGitConfig = async () => {
  gitLoading.value = true
  try {
    const res = await gitApi.getConfig()
    defaultProjectName.value = res?.default_project_name || ''
    const config = res?.config || {}
    gitConfig.value = {
      project_name:
        config.project_name || res?.project_name || defaultProjectName.value || '',
      repo_url: config.repo_url || '',
      username: config.username || '',
      branch: config.branch || 'main',
      has_password: Boolean(config.has_password)
    }
    gitPassword.value = ''
    passwordTouched.value = false
    gitStatus.value = {
      status: config.last_sync_status || null,
      message: config.last_sync_message || '',
      time: config.last_synced_at || null
    }
  } catch (error) {
    console.error('加载 Git 配置失败:', error)
    ElMessage.error(error?.detail || error?.message || '加载 Git 配置失败')
  } finally {
    gitLoading.value = false
  }
}

const handlePasswordInput = (value) => {
  gitPassword.value = value
  passwordTouched.value = true
}

const handleSaveGitConfig = async () => {
  if (!gitConfig.value.project_name?.trim()) {
    ElMessage.warning('请填写项目名称')
    return
  }
  if (!gitConfig.value.repo_url) {
    ElMessage.warning('请填写 Git 仓库地址')
    return
  }
  gitSaving.value = true
  try {
    await gitApi.saveConfig({
      project_name: gitConfig.value.project_name.trim(),
      repo_url: gitConfig.value.repo_url,
      username: gitConfig.value.username || null,
      branch: gitConfig.value.branch || 'main',
      password: passwordTouched.value ? gitPassword.value : null
    })
    ElMessage.success('Git 配置已保存')
    await loadGitConfig()
  } catch (error) {
    console.error('保存 Git 配置失败:', error)
    ElMessage.error(error?.detail || error?.message || '保存 Git 配置失败')
  } finally {
    gitSaving.value = false
  }
}

const handleSyncGit = async () => {
  gitSyncing.value = true
  try {
    const res = await gitApi.sync()
    ElMessage.success(res?.result?.message || '配置已同步到 Git')
    await loadGitConfig()
  } catch (error) {
    console.error('同步 Git 失败:', error)
    ElMessage.error(error?.detail || error?.message || '同步失败')
  } finally {
    gitSyncing.value = false
  }
}
</script>

<style scoped>
.git-sync-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}

.card-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.git-form {
  max-width: 600px;
}

.git-alert {
  margin-top: 16px;
}

.git-status {
  margin: 0;
  font-size: 14px;
}

.git-status-detail {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-muted);
}

.git-status-muted {
  color: var(--text-muted);
  margin-top: 16px;
}

.tips {
  margin: 0;
  padding-left: 16px;
}

.tips li {
  margin-bottom: 4px;
  font-size: 13px;
}

.help-text {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>

