<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-logo">
        <NginxLogo :large="true" />
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
            placeholder="用户名"
            size="large"
            prefix-icon="User"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            size="large"
            prefix-icon="Lock"
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
            登录
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'
import { ElMessage } from 'element-plus'
import NginxLogo from '../components/NginxLogo.vue'

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
  background: var(--gradient-dark);
  position: relative;
  overflow: hidden;
}

.login-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    radial-gradient(circle at 20% 50%, rgba(0, 150, 57, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 80% 80%, rgba(0, 168, 107, 0.1) 0%, transparent 50%);
  pointer-events: none;
}

.login-box {
  width: 400px;
  padding: 40px;
  background: var(--bg-card);
  border-radius: 12px;
  box-shadow: var(--shadow-lg), var(--shadow-glow);
  border: 1px solid var(--border-color);
  position: relative;
  z-index: 1;
}

.login-logo {
  text-align: center;
  margin-bottom: 30px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.login-form {
  margin-top: 20px;
}

.login-button {
  width: 100%;
  background: var(--gradient-nginx);
  border: none;
  font-weight: 500;
  letter-spacing: 1px;
}

.login-button:hover {
  box-shadow: 0 0 20px var(--nginx-green-glow);
}
</style>

