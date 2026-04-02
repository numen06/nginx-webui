<template>
  <el-container class="layout-container">
    <el-aside :width="isCollapsed ? '64px' : '200px'" class="sidebar" :class="{ 'is-collapsed': isCollapsed }">
      <div class="logo">
        <svg viewBox="0 0 120 120" class="logo-icon">
          <circle cx="60" cy="60" r="50" fill="none" stroke="var(--nginx-green)" stroke-width="3" opacity="0.3"/>
          <path d="M 30 60 L 60 30 L 90 60 L 60 90 Z" fill="var(--nginx-green)" opacity="0.8"/>
          <path d="M 40 60 L 60 40 L 80 60 L 60 80 Z" fill="var(--nginx-green)"/>
          <circle cx="60" cy="60" r="8" fill="var(--nginx-green-light)"/>
        </svg>
        <span v-if="!isCollapsed" class="logo-text">Nginx WebUI</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="sidebar-menu"
        background-color="var(--bg-secondary)"
        text-color="var(--text-secondary)"
        active-text-color="var(--nginx-green)"
        :collapse="isCollapsed"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span v-if="!isCollapsed">仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Edit /></el-icon>
          <span v-if="!isCollapsed">配置管理</span>
        </el-menu-item>
        <el-menu-item index="/logs">
          <el-icon><Document /></el-icon>
          <span v-if="!isCollapsed">日志查看</span>
        </el-menu-item>
        <el-menu-item index="/files">
          <el-icon><Folder /></el-icon>
          <span v-if="!isCollapsed">文件管理</span>
        </el-menu-item>
        <el-menu-item index="/static-package">
          <el-icon><Box /></el-icon>
          <span v-if="!isCollapsed">静态资源包</span>
        </el-menu-item>
        <el-menu-item index="/certificates">
          <el-icon><Lock /></el-icon>
          <span v-if="!isCollapsed">证书管理</span>
        </el-menu-item>
        <el-menu-item index="/audit">
          <el-icon><View /></el-icon>
          <span v-if="!isCollapsed">操作日志</span>
        </el-menu-item>
        <el-menu-item index="/nginx">
          <el-icon><Odometer /></el-icon>
          <span v-if="!isCollapsed">Nginx 管理</span>
        </el-menu-item>
        <el-menu-item index="/git-sync">
          <el-icon><Share /></el-icon>
          <span v-if="!isCollapsed">Git 配置同步</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <el-button
          class="collapse-btn"
          text
          circle
          :icon="isCollapsed ? Expand : Fold"
          @click="toggleCollapse"
        />
        <el-tooltip
          v-if="isCollapsed"
          content="版本与更新"
          placement="right"
        >
          <el-button
            class="version-info-btn"
            text
            circle
            :icon="InfoFilled"
            @click="openVersionDialog"
          />
        </el-tooltip>
        <div
          v-else-if="systemVersion.version"
          class="sidebar-version sidebar-version--clickable"
          role="button"
          tabindex="0"
          @click="openVersionDialog"
          @keydown.enter.prevent="openVersionDialog"
          @keydown.space.prevent="openVersionDialog"
        >
          <span class="version-label">系统版本</span>
          <span class="version-value">{{ systemVersion.version }}</span>
          <span
            v-if="updateStatus.hasUpdate"
            class="version-update-dot"
            title="发现新版本"
          ></span>
        </div>
      </div>
    </el-aside>
    <el-container class="content-container">
      <el-header class="header">
        <div class="header-left">
          <span>Nginx WebUI 管理系统</span>
        </div>
        <div class="header-right">
          <el-dropdown @command="handleUserCommand" trigger="click">
            <span class="user-dropdown">
              <el-icon><User /></el-icon>
              <span class="username">{{ authStore.username }}</span>
              <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>
                  <span>用户中心</span>
                </el-dropdown-item>
                <el-dropdown-item divided command="logout">
                  <el-icon><SwitchButton /></el-icon>
                  <span>退出登录</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
      
      <!-- Nginx 初始设置向导 -->
      <NginxSetupWizard
        v-model="showSetupWizard"
        @complete="handleSetupComplete"
      />
      
      <!-- 遮罩层，在设置完成前阻止其他操作 -->
      <div v-if="showSetupWizard" class="setup-overlay"></div>
      <el-footer class="footer" height="auto">
        <span>Power by numen06 · 项目地址：</span>
        <a
          href="https://gitee.com/numen06"
          target="_blank"
          rel="noopener noreferrer"
        >
          https://gitee.com/numen06
        </a>
      </el-footer>
    </el-container>
  </el-container>

  <el-dialog
      v-model="versionDialogVisible"
      title="版本与更新"
      width="520px"
      class="version-dialog"
      append-to-body
      destroy-on-close
    >
      <div v-loading="checkLoading" class="version-dialog-body">
        <el-descriptions :column="1" border size="small" class="version-desc">
          <el-descriptions-item label="当前运行版本">
            {{ displayCurrentVersion }}
          </el-descriptions-item>
          <el-descriptions-item label="Gitee 最新版本">
            {{ updateStatus.latestVersion || '—' }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="updateStatus.releaseName"
            label="Release 名称"
          >
            {{ updateStatus.releaseName }}
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="!updateStatus.checkSuccess"
          type="error"
          :closable="false"
          show-icon
          class="version-alert"
        >
          {{ updateStatus.checkMessage || '检查更新失败' }}
        </el-alert>
        <el-alert
          v-else-if="updateStatus.hasUpdate"
          type="warning"
          :closable="false"
          show-icon
          title="发现新版本"
          description="请前往 Gitee Release 下载镜像或按项目说明升级。"
          class="version-alert"
        />
        <el-alert
          v-else-if="updateStatus.latestVersion"
          type="success"
          :closable="false"
          show-icon
          title="已是最新版本"
          class="version-alert"
        />

        <template v-if="updateStatus.checkSuccess && updateStatus.releaseBody">
          <div class="version-body-label">发行说明（与 Gitee 一致）</div>
          <div class="version-release-body">{{ updateStatus.releaseBody }}</div>
        </template>
        <div
          v-else-if="
            updateStatus.checkSuccess &&
            updateStatus.latestVersion &&
            !updateStatus.releaseBody
          "
          class="version-body-empty"
        >
          本 Release 暂无正文说明，可点击「在 Gitee 查看」打开页面。
        </div>

        <div class="version-dialog-links">
          <a
            href="https://gitee.com/numen06/nginx-webui/releases"
            target="_blank"
            rel="noopener noreferrer"
          >
            全部发行版
          </a>
        </div>
      </div>
      <template #footer>
        <el-button @click="versionDialogVisible = false">关闭</el-button>
        <el-button :loading="checkLoading" @click="refreshVersionCheck">
          重新检查
        </el-button>
        <el-button
          type="primary"
          :disabled="!updateStatus.releaseUrl"
          @click="openReleaseUrl"
        >
          在 Gitee 查看
        </el-button>
      </template>
    </el-dialog>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../store/auth'
import { useSetupStore } from '../store/setup'
import { ElMessage, ElNotification } from 'element-plus'
import {
  SwitchButton,
  User,
  ArrowDown,
  Fold,
  Expand,
  InfoFilled
} from '@element-plus/icons-vue'
import { systemApi } from '../api/system'
import NginxSetupWizard from '../components/NginxSetupWizard.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const setupStore = useSetupStore()

const activeMenu = computed(() => route.path)

// 侧边栏折叠状态
const isCollapsed = ref(false)

// 系统版本信息（用于侧边栏底部展示）
const systemVersion = ref({
  version: null
})

// 构建时注入（Docker 多阶段与 backend/VERSION 同步）；开发环境通常为空
const embeddedAppVersion =
  typeof import.meta.env.VITE_APP_VERSION === 'string' &&
  import.meta.env.VITE_APP_VERSION.trim()
    ? import.meta.env.VITE_APP_VERSION.trim()
    : ''

const updateStatus = ref({
  hasUpdate: false,
  latestVersion: null,
  releaseUrl: null,
  releaseName: null,
  releaseBodySummary: null,
  currentVersion: null,
  releaseBody: null,
  checkSuccess: true,
  checkMessage: ''
})

const versionDialogVisible = ref(false)
const checkLoading = ref(false)

const displayCurrentVersion = computed(() => {
  return (
    updateStatus.value.currentVersion ||
    systemVersion.value.version ||
    '—'
  )
})

// 使用store中的状态
const showSetupWizard = computed({
  get: () => setupStore.showSetupWizard,
  set: (value) => setupStore.setShowSetupWizard(value)
})

const handleSetupComplete = () => {
  setupStore.setShowSetupWizard(false)
  ElMessage.success('Nginx 设置完成，系统已就绪')
}

const handleUserCommand = (command) => {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'logout') {
    handleLogout()
  }
}

const handleLogout = () => {
  authStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const loadSystemVersion = async () => {
  if (embeddedAppVersion) {
    systemVersion.value.version = embeddedAppVersion
  }
  try {
    const res = await systemApi.getVersion()
    if (res.success && res.version) {
      // 无构建注入时以接口为准；有注入时保持镜像内嵌版本（与 backend/VERSION 一致）
      if (!embeddedAppVersion) {
        systemVersion.value.version = res.version
      }
    }
  } catch (e) {
    // 版本信息非关键，不弹错误
    console.error('获取系统版本失败:', e)
  }
}

const loadUpdateStatus = async (options = { showLoading: false }) => {
  if (options.showLoading) {
    checkLoading.value = true
  }
  try {
    const res = await systemApi.checkUpdate()
    updateStatus.value = {
      hasUpdate: !!res.has_update,
      latestVersion: res.latest_version || null,
      releaseUrl: res.release_url || null,
      releaseName: res.release_name || null,
      releaseBodySummary: res.release_body_summary || null,
      currentVersion: res.current_version || null,
      releaseBody: res.release_body || null,
      checkSuccess: !!res.success,
      checkMessage: res.message || ''
    }

    if (res.success && res.has_update) {
      const noticeKey = `update-notified-${res.latest_version || 'unknown'}`
      if (!sessionStorage.getItem(noticeKey)) {
        const summary = res.release_body_summary
          ? `\n${res.release_body_summary}`
          : ''
        ElNotification({
          title: '发现新版本',
          message: `当前版本 ${res.current_version || '-'}，最新版本 ${res.latest_version || '-'}${summary}`,
          type: 'info',
          duration: 8000,
          onClick: () => {
            if (res.release_url) {
              window.open(res.release_url, '_blank', 'noopener,noreferrer')
            }
          }
        })
        sessionStorage.setItem(noticeKey, '1')
      }
    }
  } catch (e) {
    console.error('检查系统更新失败:', e)
    const detail =
      e?.response?.data?.detail ||
      e?.message ||
      '网络错误，检查更新失败'
    updateStatus.value = {
      ...updateStatus.value,
      checkSuccess: false,
      checkMessage: typeof detail === 'string' ? detail : '检查更新失败'
    }
  } finally {
    if (options.showLoading) {
      checkLoading.value = false
    }
  }
}

const openVersionDialog = async () => {
  versionDialogVisible.value = true
  await loadUpdateStatus({ showLoading: true })
}

const refreshVersionCheck = () => loadUpdateStatus({ showLoading: true })

const openReleaseUrl = () => {
  if (updateStatus.value.releaseUrl) {
    window.open(updateStatus.value.releaseUrl, '_blank', 'noopener,noreferrer')
  }
}

onMounted(() => {
  loadSystemVersion()
  loadUpdateStatus()
})
</script>

<style scoped>
.layout-container {
  height: 100vh;
  background-color: var(--bg-primary);
}

.content-container {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.sidebar {
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-bottom: 1px solid var(--border-color);
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
  padding: 10px;
}

.logo-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  animation: logoRotate 8s linear infinite;
}

@keyframes logoRotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  background: linear-gradient(135deg, var(--nginx-green) 0%, var(--nginx-green-light) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
  background-color: var(--bg-secondary);
}

.sidebar-footer {
  padding: 8px 12px;
  border-top: 1px solid var(--border-color);
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.sidebar-version {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-secondary);
}

.sidebar-version--clickable {
  cursor: pointer;
  border-radius: 4px;
  padding: 2px 4px;
  margin: -2px -4px;
  transition: background-color 0.2s;
}

.sidebar-version--clickable:hover {
  background-color: var(--bg-tertiary);
}

.version-info-btn {
  color: var(--nginx-green-light);
  padding: 4px;
}

.version-label {
  opacity: 0.7;
}

.version-value {
  font-weight: 500;
  color: var(--nginx-green-light);
}

.version-update-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #f56c6c;
  display: inline-block;
  box-shadow: 0 0 0 2px rgba(245, 108, 108, 0.15);
}

.collapse-btn {
  color: var(--text-secondary);
  padding: 4px;
}

.header {
  background-color: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  box-shadow: var(--shadow-sm);
}

.header-left {
  font-size: 16px;
  font-weight: bold;
  color: var(--text-primary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 15px;
}

.user-dropdown {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 4px;
  transition: background-color 0.3s;
  color: var(--text-secondary);
}

.user-dropdown:hover {
  background-color: var(--bg-tertiary);
}

.username {
  color: var(--text-secondary);
  font-weight: 500;
}

.dropdown-icon {
  font-size: 12px;
  transition: transform 0.3s;
}

.main-content {
  background-color: var(--bg-primary);
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.footer {
  background-color: var(--bg-card);
  border-top: 1px solid var(--border-color);
  text-align: center;
  padding: 4px 12px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.2;
}

.setup-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  z-index: 2000;
  pointer-events: auto;
}

.version-dialog-body {
  min-height: 80px;
}

.version-desc {
  margin-bottom: 12px;
}

.version-alert {
  margin-bottom: 12px;
}

.version-body-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.version-release-body {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 280px;
  overflow-y: auto;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
}

.version-body-empty {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.version-dialog-links {
  margin-top: 12px;
  font-size: 12px;
}

.version-dialog-links a {
  color: var(--nginx-green-light);
}
</style>

