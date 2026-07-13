<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { z } from 'zod'
import { KeyRound, Pencil, Plus, RefreshCw, Search, ShieldCheck, Trash2, UserRound } from 'lucide-vue-next'
import type { User } from '@/api/auth'
import { usersApi, type CreateUserPayload, type UpdateUserPayload } from '@/api/users'
import { apiErrorMessage } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ElMessage, ElMessageBox } from '@/lib/feedback'
import { useAuthStore } from '@/store/auth'
import { formatDateTime } from '@/utils/date'

const authStore = useAuthStore()
const users = ref<User[]>([])
const loading = ref(false)
const keyword = ref('')
const statusFilter = ref('all')
const editorOpen = ref(false)
const passwordOpen = ref(false)
const editingId = ref<number | null>(null)
const resettingUser = ref<User | null>(null)
const submitting = ref(false)
const formError = ref('')
const passwordError = ref('')

const form = reactive<CreateUserPayload>({
  username: '',
  password: '',
  is_active: true,
  is_admin: false,
})
const passwordForm = reactive({ password: '', confirm: '' })

const filteredUsers = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return users.value.filter(user => {
    const matchesQuery = !query || user.username.toLowerCase().includes(query)
    const matchesStatus = statusFilter.value === 'all'
      || (statusFilter.value === 'active' ? user.is_active : !user.is_active)
    return matchesQuery && matchesStatus
  })
})

const userSchema = z.object({
  username: z.string().trim().min(3, '用户名至少 3 个字符').max(50, '用户名最多 50 个字符'),
  password: z.string().max(100, '密码最多 100 个字符'),
  is_active: z.boolean(),
  is_admin: z.boolean(),
})

async function loadUsers() {
  loading.value = true
  try {
    const response = await usersApi.getUsers()
    users.value = response.users
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '加载用户列表失败'))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { username: '', password: '', is_active: true, is_admin: false })
  formError.value = ''
  editorOpen.value = true
}

function openEdit(user: User) {
  editingId.value = user.id
  Object.assign(form, {
    username: user.username,
    password: '',
    is_active: user.is_active,
    is_admin: user.is_admin,
  })
  formError.value = ''
  editorOpen.value = true
}

async function submitUser() {
  const parsed = userSchema.safeParse(form)
  if (!parsed.success) {
    formError.value = parsed.error.issues[0]?.message || '请检查表单内容'
    return
  }
  if (editingId.value == null && form.password.length < 6) {
    formError.value = '密码至少 6 个字符'
    return
  }

  submitting.value = true
  formError.value = ''
  try {
    if (editingId.value == null) {
      await usersApi.createUser(parsed.data as CreateUserPayload)
      ElMessage.success('用户创建成功')
    } else {
      const payload: UpdateUserPayload = {
        username: parsed.data.username,
        is_active: parsed.data.is_active,
        is_admin: parsed.data.is_admin,
      }
      await usersApi.updateUser(editingId.value, payload)
      ElMessage.success('用户信息已更新')
      if (editingId.value === authStore.user?.id) await authStore.ensureUser(true)
    }
    editorOpen.value = false
    await loadUsers()
  } catch (error) {
    formError.value = apiErrorMessage(error)
  } finally {
    submitting.value = false
  }
}

function openPasswordReset(user: User) {
  resettingUser.value = user
  Object.assign(passwordForm, { password: '', confirm: '' })
  passwordError.value = ''
  passwordOpen.value = true
}

async function submitPasswordReset() {
  if (passwordForm.password.length < 6) {
    passwordError.value = '密码至少 6 个字符'
    return
  }
  if (passwordForm.password !== passwordForm.confirm) {
    passwordError.value = '两次输入的密码不一致'
    return
  }
  if (!resettingUser.value) return
  submitting.value = true
  try {
    await usersApi.resetPassword(resettingUser.value.id, passwordForm.password)
    ElMessage.success('密码重置成功')
    passwordOpen.value = false
  } catch (error) {
    passwordError.value = apiErrorMessage(error, '密码重置失败')
  } finally {
    submitting.value = false
  }
}

async function deleteUser(user: User) {
  try {
    await ElMessageBox.confirm(`确定删除用户“${user.username}”吗？此操作不可恢复。`, '删除用户')
    await usersApi.deleteUser(user.id)
    ElMessage.success('用户已删除')
    await loadUsers()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '删除失败'))
  }
}

onMounted(loadUsers)
</script>

<template>
  <div class="page-shell">
    <div class="page-heading">
      <div>
        <h2 class="page-title">用户管理</h2>
        <p class="page-description">管理系统账户、状态与超级管理员权限。</p>
      </div>
      <div class="toolbar">
        <Button variant="secondary" :disabled="loading" @click="loadUsers">
          <RefreshCw :class="['size-4', { 'animate-spin': loading }]" />刷新
        </Button>
        <Button @click="openCreate"><Plus class="size-4" />新增用户</Button>
      </div>
    </div>

    <Card class="gap-0 py-0">
      <CardHeader class="border-b p-4 md:p-5">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle class="text-base">账户列表</CardTitle>
          <div class="flex flex-col gap-2 sm:flex-row">
            <div class="relative sm:w-64">
              <Search class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input v-model="keyword" class="pl-9" placeholder="搜索用户名" />
            </div>
            <Select v-model="statusFilter">
              <SelectTrigger class="sm:w-36"><SelectValue placeholder="账户状态" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="active">已启用</SelectItem>
                <SelectItem value="inactive">已停用</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent class="p-0">
        <div class="hidden overflow-x-auto md:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>用户</TableHead><TableHead>权限</TableHead><TableHead>状态</TableHead><TableHead>创建时间</TableHead><TableHead class="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="user in filteredUsers" :key="user.id">
                <TableCell><div class="flex items-center gap-2"><UserRound class="size-4 text-muted-foreground" /><span class="font-medium">{{ user.username }}</span><Badge v-if="user.id === authStore.user?.id" variant="outline">当前账户</Badge></div></TableCell>
                <TableCell><Badge :variant="user.is_admin ? 'default' : 'secondary'"><ShieldCheck v-if="user.is_admin" class="mr-1 size-3" />{{ user.is_admin ? '超级管理员' : '普通用户' }}</Badge></TableCell>
                <TableCell><Badge :variant="user.is_active ? 'outline' : 'destructive'">{{ user.is_active ? '已启用' : '已停用' }}</Badge></TableCell>
                <TableCell class="text-muted-foreground">{{ formatDateTime(user.created_at) }}</TableCell>
                <TableCell><div class="flex justify-end gap-1"><Button size="icon" variant="ghost" title="编辑" @click="openEdit(user)"><Pencil class="size-4" /></Button><Button size="icon" variant="ghost" title="重置密码" @click="openPasswordReset(user)"><KeyRound class="size-4" /></Button><Button size="icon" variant="ghost" title="删除" :disabled="user.id === authStore.user?.id" @click="deleteUser(user)"><Trash2 class="size-4 text-destructive" /></Button></div></TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        <div class="grid gap-3 p-4 md:hidden">
          <div v-for="user in filteredUsers" :key="user.id" class="space-y-3 rounded-lg border p-4">
            <div class="flex items-start justify-between gap-3"><div><div class="font-medium">{{ user.username }}</div><div class="mt-1 text-xs text-muted-foreground">{{ formatDateTime(user.created_at) }}</div></div><Badge :variant="user.is_active ? 'outline' : 'destructive'">{{ user.is_active ? '已启用' : '已停用' }}</Badge></div>
            <Badge :variant="user.is_admin ? 'default' : 'secondary'">{{ user.is_admin ? '超级管理员' : '普通用户' }}</Badge>
            <div class="flex gap-2"><Button size="sm" variant="secondary" @click="openEdit(user)"><Pencil class="size-4" />编辑</Button><Button size="sm" variant="secondary" @click="openPasswordReset(user)"><KeyRound class="size-4" />重置密码</Button></div>
          </div>
        </div>

        <div v-if="!loading && !filteredUsers.length" class="grid min-h-36 place-items-center text-sm text-muted-foreground">没有符合条件的用户</div>
      </CardContent>
    </Card>
  </div>

  <Dialog v-model:open="editorOpen">
    <DialogContent>
      <DialogHeader><DialogTitle>{{ editingId == null ? '新增用户' : '编辑用户' }}</DialogTitle><DialogDescription>设置登录名称、账户状态与管理权限。</DialogDescription></DialogHeader>
      <form class="space-y-4" @submit.prevent="submitUser">
        <div class="space-y-2"><Label for="user-name">用户名</Label><Input id="user-name" v-model="form.username" autocomplete="off" /></div>
        <div v-if="editingId == null" class="space-y-2"><Label for="user-password">初始密码</Label><Input id="user-password" v-model="form.password" type="password" autocomplete="new-password" /></div>
        <div class="flex items-center justify-between rounded-lg border p-3"><div><Label>启用账户</Label><p class="text-xs text-muted-foreground">停用后该用户无法登录。</p></div><Switch v-model="form.is_active" /></div>
        <div class="flex items-start gap-3 rounded-lg border p-3"><Checkbox id="is-admin" v-model="form.is_admin" /><div><Label for="is-admin">超级管理员</Label><p class="text-xs text-muted-foreground">允许管理用户及重置其他账户密码。</p></div></div>
        <p v-if="formError" class="text-sm text-destructive">{{ formError }}</p>
        <DialogFooter><Button type="button" variant="secondary" @click="editorOpen = false">取消</Button><Button type="submit" :disabled="submitting">{{ submitting ? '保存中…' : '保存' }}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>

  <Dialog v-model:open="passwordOpen">
    <DialogContent>
      <DialogHeader><DialogTitle>重置密码</DialogTitle><DialogDescription>为 {{ resettingUser?.username }} 设置新的登录密码。</DialogDescription></DialogHeader>
      <form class="space-y-4" @submit.prevent="submitPasswordReset">
        <div class="space-y-2"><Label for="reset-password">新密码</Label><Input id="reset-password" v-model="passwordForm.password" type="password" autocomplete="new-password" /></div>
        <div class="space-y-2"><Label for="confirm-password">确认新密码</Label><Input id="confirm-password" v-model="passwordForm.confirm" type="password" autocomplete="new-password" /></div>
        <p v-if="passwordError" class="text-sm text-destructive">{{ passwordError }}</p>
        <DialogFooter><Button type="button" variant="secondary" @click="passwordOpen = false">取消</Button><Button type="submit" :disabled="submitting">确认重置</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
