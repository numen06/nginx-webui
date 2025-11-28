<template>
  <div class="users-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>用户管理</span>
          <div>
            <el-button type="info" @click="handleChangePassword">
              <el-icon><Lock /></el-icon>
              <span class="btn-label">修改我的密码</span>
            </el-button>
            <el-button type="primary" @click="handleCreate">
              <el-icon><CirclePlus /></el-icon>
              <span class="btn-label">新增用户</span>
            </el-button>
          </div>
        </div>
      </template>
      <div class="table-toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索用户名"
          clearable
          class="toolbar-field"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="statusFilter" class="toolbar-field status-filter">
          <el-option label="全部状态" value="all" />
          <el-option label="激活" value="active" />
          <el-option label="禁用" value="inactive" />
        </el-select>
        <div class="toolbar-actions">
          <el-button @click="handleRefresh">
            <el-icon><Refresh /></el-icon>
            <span class="btn-label">刷新</span>
          </el-button>
        </div>
      </div>
      <el-table :data="filteredUsers" style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="100" align="center" />
        <el-table-column
          prop="username"
          label="用户名"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column prop="is_active" label="状态" width="120" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.is_active ? 'success' : 'danger'">
              {{ scope.row.is_active ? '激活' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          label="创建时间"
          min-width="180"
          align="center"
        >
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" align="center">
          <template #default="scope">
            <el-button size="small" type="info" @click="handleEdit(scope.row)">
              <el-icon><Edit /></el-icon>
              <span class="btn-label">编辑</span>
            </el-button>
            <el-button size="small" type="warning" @click="handleResetPassword(scope.row)">
              <el-icon><Key /></el-icon>
              <span class="btn-label">重置密码</span>
            </el-button>
            <el-button 
              size="small" 
              type="danger" 
              @click="handleDelete(scope.row)"
              :disabled="scope.row.id === currentUserId"
            >
              <el-icon><Delete /></el-icon>
              <span class="btn-label">删除</span>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑用户对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form :model="formData" :rules="formRules" ref="formRef" label-width="100px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="formData.username" :disabled="isEdit" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="密码" prop="password">
          <el-input v-model="formData.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="formData.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="dialogVisible = false">
            <el-icon><CloseBold /></el-icon>
            <span class="btn-label">取消</span>
          </el-button>
          <el-button type="primary" @click="handleSubmit">
            <el-icon><Check /></el-icon>
            <span class="btn-label">确定</span>
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog
      v-model="passwordDialogVisible"
      title="重置密码"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form :model="passwordForm" :rules="passwordRules" ref="passwordFormRef" label-width="100px">
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="passwordForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input v-model="passwordForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="passwordDialogVisible = false">
            <el-icon><CloseBold /></el-icon>
            <span class="btn-label">取消</span>
          </el-button>
          <el-button type="primary" @click="handlePasswordSubmit">
            <el-icon><Check /></el-icon>
            <span class="btn-label">确定</span>
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 修改当前用户密码对话框 -->
    <el-dialog
      v-model="changePasswordDialogVisible"
      title="修改密码"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form :model="changePasswordForm" :rules="changePasswordRules" ref="changePasswordFormRef" label-width="100px">
        <el-form-item label="旧密码" prop="old_password">
          <el-input v-model="changePasswordForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="changePasswordForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input v-model="changePasswordForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button type="info" @click="changePasswordDialogVisible = false">
            <el-icon><CloseBold /></el-icon>
            <span class="btn-label">取消</span>
          </el-button>
          <el-button type="primary" @click="handleChangePasswordSubmit">
            <el-icon><Check /></el-icon>
            <span class="btn-label">确定</span>
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { usersApi } from '../api/users'
import { useAuthStore } from '../store/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Lock, CirclePlus, Edit, Key, Delete, CloseBold, Check, Search, Refresh } from '@element-plus/icons-vue'
import { formatDateTime } from '../utils/date'

const authStore = useAuthStore()
const userList = ref([])
const loading = ref(false)
const keyword = ref('')
const statusFilter = ref('all')
const dialogVisible = ref(false)
const passwordDialogVisible = ref(false)
const changePasswordDialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const passwordFormRef = ref(null)
const changePasswordFormRef = ref(null)
const currentEditUserId = ref(null)
const currentResetPasswordUserId = ref(null)

const currentUserId = computed(() => {
  return authStore.user?.id
})

const filteredUsers = computed(() => {
  const keywordValue = keyword.value.trim().toLowerCase()
  return userList.value.filter((user) => {
    const matchKeyword = keywordValue
      ? user.username.toLowerCase().includes(keywordValue)
      : true
    const matchStatus =
      statusFilter.value === 'all'
        ? true
        : statusFilter.value === 'active'
          ? user.is_active
          : !user.is_active
    return matchKeyword && matchStatus
  })
})

const dialogTitle = computed(() => {
  return isEdit.value ? '编辑用户' : '新增用户'
})

const formData = ref({
  username: '',
  password: '',
  is_active: true
})

const passwordForm = ref({
  new_password: '',
  confirm_password: ''
})

const changePasswordForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

// 验证确认密码
const validateConfirmPassword = (rule, value, callback) => {
  if (value !== passwordForm.value.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

// 验证修改密码的确认密码
const validateChangePasswordConfirm = (rule, value, callback) => {
  if (value !== changePasswordForm.value.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const formRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度在 3 到 50 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度在 6 到 100 个字符', trigger: 'blur' }
  ]
}

const passwordRules = {
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度在 6 到 100 个字符', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const changePasswordRules = {
  old_password: [
    { required: true, message: '请输入旧密码', trigger: 'blur' }
  ],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度在 6 到 100 个字符', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateChangePasswordConfirm, trigger: 'blur' }
  ]
}

const loadUsers = async () => {
  loading.value = true
  try {
    const response = await usersApi.getUsers()
    userList.value = response.users || []
  } catch (error) {
    ElMessage.error('加载用户列表失败')
  } finally {
    loading.value = false
  }
}

const handleCreate = () => {
  isEdit.value = false
  currentEditUserId.value = null
  formData.value = {
    username: '',
    password: '',
    is_active: true
  }
  dialogVisible.value = true
}

const handleRefresh = () => {
  loadUsers()
}

const handleEdit = (user) => {
  isEdit.value = true
  currentEditUserId.value = user.id
  formData.value = {
    username: user.username,
    password: '',
    is_active: user.is_active
  }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    try {
      if (isEdit.value) {
        const updateData = {
          username: formData.value.username,
          is_active: formData.value.is_active
        }
        await usersApi.updateUser(currentEditUserId.value, updateData)
        ElMessage.success('用户信息更新成功')
      } else {
        await usersApi.createUser(formData.value)
        ElMessage.success('用户创建成功')
      }
      dialogVisible.value = false
      loadUsers()
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || '操作失败')
    }
  })
}

const handleResetPassword = (user) => {
  currentResetPasswordUserId.value = user.id
  passwordForm.value = {
    new_password: '',
    confirm_password: ''
  }
  passwordDialogVisible.value = true
}

const handlePasswordSubmit = async () => {
  if (!passwordFormRef.value) return
  
  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    try {
      await usersApi.resetPassword(currentResetPasswordUserId.value, passwordForm.value.new_password)
      ElMessage.success('密码重置成功')
      passwordDialogVisible.value = false
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || '密码重置失败')
    }
  })
}

const handleDelete = async (user) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${user.username}" 吗？此操作不可恢复。`,
      '提示',
      { type: 'warning' }
    )
    await usersApi.deleteUser(user.id)
    ElMessage.success('删除成功')
    loadUsers()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '删除失败')
    }
  }
}

const handleChangePassword = () => {
  changePasswordForm.value = {
    old_password: '',
    new_password: '',
    confirm_password: ''
  }
  changePasswordDialogVisible.value = true
}

const handleChangePasswordSubmit = async () => {
  if (!changePasswordFormRef.value) return
  
  await changePasswordFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    try {
      await usersApi.changePassword(
        changePasswordForm.value.old_password,
        changePasswordForm.value.new_password
      )
      ElMessage.success('密码修改成功，请重新登录')
      changePasswordDialogVisible.value = false
      // 可以选择是否自动退出登录
      setTimeout(() => {
        authStore.logout()
        window.location.href = '/login'
      }, 1500)
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || '密码修改失败')
    }
  })
}

onMounted(() => {
  loadUsers()
})
</script>

<style scoped>
.users-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.table-toolbar {
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.toolbar-field {
  flex: 1 1 220px;
}

.status-filter {
  max-width: 160px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
}

.toolbar-actions .el-button {
  margin-left: auto;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>

