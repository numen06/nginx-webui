<template>
  <el-container class="layout-container">
    <el-aside width="200px" class="sidebar">
      <div class="logo">
        <svg viewBox="0 0 120 120" class="logo-icon">
          <circle cx="60" cy="60" r="50" fill="none" stroke="var(--nginx-green)" stroke-width="3" opacity="0.3"/>
          <path d="M 30 60 L 60 30 L 90 60 L 60 90 Z" fill="var(--nginx-green)" opacity="0.8"/>
          <path d="M 40 60 L 60 40 L 80 60 L 60 80 Z" fill="var(--nginx-green)"/>
          <circle cx="60" cy="60" r="8" fill="var(--nginx-green-light)"/>
        </svg>
        <span class="logo-text">Nginx WebUI</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="sidebar-menu"
        background-color="var(--bg-secondary)"
        text-color="var(--text-secondary)"
        active-text-color="var(--nginx-green)"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Edit /></el-icon>
          <span>配置管理</span>
        </el-menu-item>
        <el-menu-item index="/logs">
          <el-icon><Document /></el-icon>
          <span>日志查看</span>
        </el-menu-item>
        <el-menu-item index="/files">
          <el-icon><Folder /></el-icon>
          <span>文件管理</span>
        </el-menu-item>
        <el-menu-item index="/static-package">
          <el-icon><Box /></el-icon>
          <span>静态资源包</span>
        </el-menu-item>
        <el-menu-item index="/certificates">
          <el-icon><Lock /></el-icon>
          <span>证书管理</span>
        </el-menu-item>
        <el-menu-item index="/audit">
          <el-icon><View /></el-icon>
          <span>操作日志</span>
        </el-menu-item>
        <el-menu-item index="/nginx">
          <el-icon><Odometer /></el-icon>
          <span>Nginx 管理</span>
        </el-menu-item>
        <el-menu-item index="/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item index="/git-sync">
          <el-icon><Share /></el-icon>
          <span>Git 配置同步</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container class="content-container">
      <el-header class="header">
        <div class="header-left">
          <span>Nginx WebUI 管理系统</span>
        </div>
        <div class="header-right">
          <span class="username">{{ authStore.username }}</span>
          <el-button type="danger" size="small" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            <span class="btn-label">退出</span>
          </el-button>
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
</template>

<script setup>
import { computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../store/auth'
import { useSetupStore } from '../store/setup'
import { ElMessage } from 'element-plus'
import { SwitchButton } from '@element-plus/icons-vue'
import NginxSetupWizard from '../components/NginxSetupWizard.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const setupStore = useSetupStore()

const activeMenu = computed(() => route.path)

// 使用store中的状态
const showSetupWizard = computed({
  get: () => setupStore.showSetupWizard,
  set: (value) => setupStore.setShowSetupWizard(value)
})

const handleSetupComplete = () => {
  setupStore.setShowSetupWizard(false)
  ElMessage.success('Nginx 设置完成，系统已就绪')
}

const handleLogout = () => {
  authStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}
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
  height: calc(100vh - 60px);
  overflow-y: auto;
  background-color: var(--bg-secondary);
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

.username {
  color: var(--text-secondary);
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
</style>

