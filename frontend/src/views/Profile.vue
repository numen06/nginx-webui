<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { z } from 'zod'
import { KeyRound, ShieldAlert, ShieldCheck, UserRound } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ElMessage } from '@/lib/feedback'
import { apiErrorMessage } from '@/api'
import { usersApi } from '@/api/users'
import { useAuthStore } from '@/store/auth'
import { formatDateTime } from '@/utils/date'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const oldPasswordInput = ref<{ $el?: HTMLInputElement }>()
const user = computed(() => authStore.user)
const isDefaultPassword = computed(() => Boolean(user.value?.is_default_password))

const schema = toTypedSchema(z.object({
  oldPassword: z.string().min(1, '请输入旧密码'),
  newPassword: z.string().min(6, '新密码至少 6 个字符').max(100, '新密码最多 100 个字符'),
  confirmPassword: z.string().min(1, '请再次输入新密码'),
}).refine(values => values.newPassword === values.confirmPassword, {
  message: '两次输入的新密码不一致',
  path: ['confirmPassword'],
}))
const { defineField, errors, handleSubmit, resetForm } = useForm({ validationSchema: schema })
const [oldPassword, oldPasswordAttrs] = defineField('oldPassword')
const [newPassword, newPasswordAttrs] = defineField('newPassword')
const [confirmPassword, confirmPasswordAttrs] = defineField('confirmPassword')

const submit = handleSubmit(async (values) => {
  loading.value = true
  try {
    await usersApi.changePassword(values.oldPassword, values.newPassword)
    ElMessage.success('密码修改成功，请重新登录')
    authStore.logout()
    await router.replace('/login')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '修改密码失败'))
  } finally {
    loading.value = false
  }
})

onMounted(async () => {
  await authStore.ensureUser(true)
  if (isDefaultPassword.value) await nextTick(() => oldPasswordInput.value?.$el?.focus())
})
</script>

<template>
  <div class="page-shell max-w-5xl">
    <div>
      <h2 class="page-title">用户中心</h2>
      <p class="page-description">查看当前账户信息并更新登录密码。</p>
    </div>

    <div v-if="isDefaultPassword" class="flex gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-amber-100">
      <ShieldAlert class="mt-0.5 size-5 shrink-0" />
      <div><div class="font-medium">正在使用默认密码</div><p class="mt-1 text-sm text-amber-100/75">请立即修改密码，修改后需要重新登录。</p></div>
    </div>

    <div class="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
      <Card>
        <CardHeader><CardTitle class="flex items-center gap-2 text-base"><UserRound class="size-4" />账户信息</CardTitle></CardHeader>
        <CardContent class="space-y-4 text-sm">
          <div class="flex items-center justify-between gap-4 border-b pb-3"><span class="text-muted-foreground">用户名</span><span class="font-medium">{{ user?.username || '—' }}</span></div>
          <div class="flex items-center justify-between gap-4 border-b pb-3"><span class="text-muted-foreground">账户状态</span><Badge :variant="user?.is_active ? 'outline' : 'destructive'">{{ user?.is_active ? '已启用' : '已停用' }}</Badge></div>
          <div class="flex items-center justify-between gap-4 border-b pb-3"><span class="text-muted-foreground">账户权限</span><Badge :variant="user?.is_admin ? 'default' : 'secondary'"><ShieldCheck v-if="user?.is_admin" class="mr-1 size-3" />{{ user?.is_admin ? '超级管理员' : '普通用户' }}</Badge></div>
          <div class="flex items-center justify-between gap-4"><span class="text-muted-foreground">创建时间</span><span>{{ formatDateTime(user?.created_at) }}</span></div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle class="flex items-center gap-2 text-base"><KeyRound class="size-4" />修改密码</CardTitle><CardDescription>新密码长度为 6–100 个字符。</CardDescription></CardHeader>
        <CardContent>
          <form class="space-y-4" @submit="submit">
            <div class="space-y-2"><Label for="old-password">旧密码</Label><Input id="old-password" ref="oldPasswordInput" v-model="oldPassword" v-bind="oldPasswordAttrs" type="password" autocomplete="current-password" /><p v-if="errors.oldPassword" class="text-sm text-destructive">{{ errors.oldPassword }}</p></div>
            <div class="space-y-2"><Label for="new-password">新密码</Label><Input id="new-password" v-model="newPassword" v-bind="newPasswordAttrs" type="password" autocomplete="new-password" /><p v-if="errors.newPassword" class="text-sm text-destructive">{{ errors.newPassword }}</p></div>
            <div class="space-y-2"><Label for="confirm-password">确认新密码</Label><Input id="confirm-password" v-model="confirmPassword" v-bind="confirmPasswordAttrs" type="password" autocomplete="new-password" /><p v-if="errors.confirmPassword" class="text-sm text-destructive">{{ errors.confirmPassword }}</p></div>
            <div class="flex justify-end gap-2"><Button type="button" variant="secondary" @click="resetForm()">重置</Button><Button type="submit" :disabled="loading">{{ loading ? '提交中…' : '修改密码' }}</Button></div>
          </form>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
