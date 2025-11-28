<template>
  <div class="login-container">
    <div class="login-background">
      <div class="bg-decoration"></div>
    </div>
    <div class="login-content">
    <div class="login-box">
        <div class="login-header">
          <div class="login-logo">
            <svg viewBox="0 0 120 120" class="logo-icon">
              <circle cx="60" cy="60" r="50" fill="none" stroke="var(--nginx-green)" stroke-width="3" opacity="0.3"/>
              <path d="M 30 60 L 60 30 L 90 60 L 60 90 Z" fill="var(--nginx-green)" opacity="0.8"/>
              <path d="M 40 60 L 60 40 L 80 60 L 60 80 Z" fill="var(--nginx-green)"/>
              <circle cx="60" cy="60" r="8" fill="var(--nginx-green-light)"/>
            </svg>
          </div>
          <p class="login-subtitle">Nginx WebUI · 可视化 Nginx 配置管理系统</p>
        </div>
      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
              placeholder="请输入用户名"
            size="large"
            prefix-icon="User"
              clearable
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
              placeholder="请输入密码"
            size="large"
            prefix-icon="Lock"
              show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-button"
            :loading="loading"
            @click="handleLogin"
          >
              <span v-if="!loading">登录</span>
              <span v-else>登录中...</span>
          </el-button>
        </el-form-item>
      </el-form>
        <div class="login-tips">
          <el-alert
            :closable="false"
            type="info"
            show-icon
            class="tips-alert"
          >
            <template #title>
              <span class="tips-text">提示：请使用管理员账号登录系统</span>
            </template>
          </el-alert>
        </div>
        <div class="login-footer">
          <span>Power by numen06 · 项目地址：</span>
          <a
            href="https://gitee.com/numen06"
            target="_blank"
            rel="noopener noreferrer"
          >
            https://gitee.com/numen06
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()

const loginFormRef = ref(null)
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: ''
})

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  if (!loginFormRef.value) return
  
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      const result = await authStore.login(loginForm.username, loginForm.password)
      if (result.success) {
        ElMessage.success('登录成功')
        router.push('/')
      } else {
        console.error('登录失败:', result)
        ElMessage.error(result.message || '登录失败，请检查用户名和密码')
      }
    } catch (error) {
      console.error('登录异常:', error)
      ElMessage.error(error?.detail || error?.message || '登录失败，请检查网络连接')
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-container {
  width: 100%;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  position: relative;
  overflow: hidden;
}

.login-background {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  overflow: hidden;
}

.bg-decoration {
  position: absolute;
  width: 200%;
  height: 200%;
  top: -50%;
  left: -50%;
  background: radial-gradient(
    circle at 30% 50%,
    rgba(8, 196, 97, 0.08) 0%,
    transparent 50%
  ),
  radial-gradient(
    circle at 70% 50%,
    rgba(59, 130, 246, 0.06) 0%,
    transparent 50%
  );
  animation: rotate 20s linear infinite;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.login-content {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 1;
  padding: 20px;
  width: 100%;
  height: 100%;
}

.login-box {
  width: 100%;
  max-width: 440px;
  padding: 48px 40px;
  background: var(--bg-card);
  border-radius: 16px;
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.4),
    0 0 0 1px var(--border-color),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-color);
  backdrop-filter: blur(10px);
  animation: fadeInUp 0.6s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
}

.login-logo {
  margin-bottom: 20px;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  animation: logoFloat 3s ease-in-out infinite;
}

.logo-icon {
  width: 80px;
  height: 80px;
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

@keyframes logoFloat {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-8px);
  }
}

.login-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
  font-weight: 400;
  letter-spacing: 0.3px;
}

.login-form {
  margin-top: 8px;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 24px;
}

.login-form :deep(.el-input__wrapper) {
  background-color: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  box-shadow: none;
  transition: all 0.3s ease;
}

.login-form :deep(.el-input__wrapper:hover) {
  border-color: var(--nginx-green);
  box-shadow: 0 0 0 2px rgba(8, 196, 97, 0.1);
}

.login-form :deep(.el-input__wrapper.is-focus) {
  border-color: var(--nginx-green);
  box-shadow: 0 0 0 2px rgba(8, 196, 97, 0.2);
}

.login-form :deep(.el-input__inner) {
  color: var(--text-primary);
}

.login-form :deep(.el-input__inner::placeholder) {
  color: var(--text-muted);
}

.login-button {
  width: 100%;
  height: 44px;
  background: var(--gradient-nginx);
  border: none;
  font-weight: 600;
  letter-spacing: 1px;
  font-size: 15px;
  transition: all 0.3s ease;
  box-shadow: 0 4px 12px rgba(8, 196, 97, 0.3);
}

.login-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(8, 196, 97, 0.4);
}

.login-button:active {
  transform: translateY(0);
}

.login-tips {
  margin-top: 24px;
}

.tips-alert {
  background-color: var(--bg-tertiary);
  border: 1px solid var(--border-color);
}

.tips-alert :deep(.el-alert__content) {
  padding: 0;
}

.tips-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.login-footer {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
  text-align: center;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.login-footer a {
  color: var(--nginx-green);
  text-decoration: none;
  transition: all 0.2s;
  font-weight: 500;
}

.login-footer a:hover {
  opacity: 0.8;
  text-decoration: underline;
}

/* 响应式设计 */
@media (max-width: 480px) {
  .login-box {
    padding: 36px 24px;
    border-radius: 12px;
  }

  .login-subtitle {
    font-size: 13px;
  }
}
</style>

