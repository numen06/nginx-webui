<template>
  <div class="profile-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>用户中心</span>
        </div>
      </template>

      <!-- 默认密码提示 -->
      <el-alert
        v-if="isDefaultPassword"
        title="安全提示"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 20px"
      >
        <template #default>
          <div>
            <p>您当前使用的是默认账号密码（admin/admin），为了系统安全，请立即修改密码。</p>
          </div>
        </template>
      </el-alert>

      <!-- 用户信息 -->
      <el-descriptions title="用户信息" :column="2" border>
        <el-descriptions-item label="用户名">
          {{ userInfo.username }}
        </el-descriptions-item>
        <el-descriptions-item label="用户ID">
          {{ userInfo.id }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="userInfo.is_active ? 'success' : 'danger'">
            {{ userInfo.is_active ? '激活' : '禁用' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ formatDateTime(userInfo.created_at) }}
        </el-descriptions-item>
      </el-descriptions>

      <!-- 修改密码 -->
      <el-divider content-position="left">
        <span style="font-size: 16px; font-weight: 600">修改密码</span>
      </el-divider>

      <el-form
        :model="passwordForm"
        :rules="passwordRules"
        ref="passwordFormRef"
        label-width="120px"
        style="max-width: 500px"
      >
        <el-form-item label="旧密码" prop="old_password">
          <el-input
            v-model="passwordForm.old_password"
            type="password"
            show-password
            placeholder="请输入当前密码"
          />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input
            v-model="passwordForm.new_password"
            type="password"
            show-password
            placeholder="请输入新密码（至少6位）"
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input
            v-model="passwordForm.confirm_password"
            type="password"
            show-password
            placeholder="请再次输入新密码"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleChangePassword" :loading="changingPassword">
            <el-icon><Check /></el-icon>
            <span class="btn-label">修改密码</span>
          </el-button>
          <el-button @click="handleReset">
            <el-icon><Refresh /></el-icon>
            <span class="btn-label">重置</span>
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'
import { authApi } from '../api/auth'
import { usersApi } from '../api/users'
import { ElMessage } from 'element-plus'
import { Check, Refresh } from '@element-plus/icons-vue'
import { formatDateTime } from '../utils/date'

const router = useRouter()

const authStore = useAuthStore()
const userInfo = ref({
  id: null,
  username: '',
  is_active: true,
  created_at: null,
  is_default_password: false
})
const passwordForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: ''
})
const passwordFormRef = ref(null)
const changingPassword = ref(false)

const isDefaultPassword = computed(() => {
  return userInfo.value.is_default_password === true
})

// 验证确认密码
const validateConfirmPassword = (rule, value, callback) => {
  if (value !== passwordForm.value.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const passwordRules = {
  old_password: [
    { required: true, message: '请输入旧密码', trigger: 'blur' }
  ],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度在 6 到 100 个字符', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const loadUserInfo = async () => {
  try {
    const response = await authApi.getCurrentUser()
    userInfo.value = response.user
    // 如果是默认密码，自动聚焦到旧密码输入框
    if (response.user?.is_default_password === true) {
      await nextTick()
      // 自动聚焦到旧密码输入框，提示用户修改密码
      const oldPasswordInput = document.querySelector('input[type="password"]')
      if (oldPasswordInput) {
        oldPasswordInput.focus()
      }
    }
  } catch (error) {
    ElMessage.error('获取用户信息失败')
  }
}

// 监听默认密码状态变化
watch(isDefaultPassword, (newVal) => {
  if (newVal) {
    nextTick(() => {
      const oldPasswordInput = document.querySelector('input[type="password"]')
      if (oldPasswordInput) {
        oldPasswordInput.focus()
      }
    })
  }
})

const handleChangePassword = async () => {
  if (!passwordFormRef.value) return

  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return

    changingPassword.value = true
    try {
      // 确保数据格式正确
      const oldPassword = String(passwordForm.value.old_password || '').trim()
      const newPassword = String(passwordForm.value.new_password || '').trim()
      
      if (!oldPassword) {
        ElMessage.error('请输入旧密码')
        changingPassword.value = false
        return
      }
      
      if (!newPassword || newPassword.length < 6) {
        ElMessage.error('新密码长度至少为 6 个字符')
        changingPassword.value = false
        return
      }
      
      await usersApi.changePassword(oldPassword, newPassword)
      ElMessage.success('密码修改成功，请重新登录')
      
      // 更新用户信息，清除默认密码标志
      if (userInfo.value) {
        userInfo.value.is_default_password = false
        authStore.setUser({ ...userInfo.value })
      }
      
      // 立即退出登录并跳转，避免页面卡死
      authStore.logout()
      // 使用 router.push 而不是 window.location.href，避免页面卡死
      router.push('/login')
    } catch (error) {
      console.error('修改密码错误:', error)
      let errorMessage = '密码修改失败'
      
      // 处理 422 验证错误
      if (error.response?.status === 422) {
        const validationErrors = error.response.data?.detail || []
        if (Array.isArray(validationErrors) && validationErrors.length > 0) {
          // 提取所有验证错误信息
          const errorMessages = validationErrors.map(err => {
            const field = err.loc?.join('.') || '字段'
            return `${field}: ${err.msg}`
          }).join('; ')
          errorMessage = `验证失败: ${errorMessages}`
        } else if (typeof validationErrors === 'string') {
          errorMessage = validationErrors
        } else {
          errorMessage = '请求参数验证失败，请检查输入是否正确'
        }
      } else if (error.detail) {
        errorMessage = error.detail
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail
      } else if (error.message) {
        errorMessage = error.message
      }
      
      ElMessage.error(errorMessage)
    } finally {
      changingPassword.value = false
    }
  })
}

const handleReset = () => {
  passwordForm.value = {
    old_password: '',
    new_password: '',
    confirm_password: ''
  }
  if (passwordFormRef.value) {
    passwordFormRef.value.clearValidate()
  }
}

onMounted(() => {
  loadUserInfo()
})
</script>

<style scoped>
.profile-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.btn-label {
  margin-left: 4px;
}
</style>

