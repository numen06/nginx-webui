<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { z } from 'zod'
import { Boxes, LockKeyhole, User } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ElMessage } from '@/lib/feedback'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const loading = ref(false)

const schema = toTypedSchema(z.object({
  username: z.string().trim().min(1, '请输入用户名'),
  password: z.string().min(1, '请输入密码'),
}))
const { defineField, errors, handleSubmit } = useForm({ validationSchema: schema })
const [username, usernameAttrs] = defineField('username')
const [password, passwordAttrs] = defineField('password')
const redirectTarget = computed(() => typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard')

const submit = handleSubmit(async (values) => {
  loading.value = true
  try {
    const result = await authStore.login(values.username, values.password)
    if (!result.success) {
      ElMessage.error(result.message || '登录失败，请检查用户名和密码')
      return
    }
    ElMessage.success('登录成功')
    if (result.isDefaultPassword) {
      ElMessage.warning('检测到默认密码，请立即修改密码')
      await router.replace('/profile')
    } else {
      await router.replace(redirectTarget.value)
    }
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="grid min-h-svh place-items-center bg-background px-4 py-10">
    <div class="w-full max-w-md space-y-6">
      <div class="flex items-center justify-center gap-3">
        <span class="grid size-11 place-items-center rounded-xl bg-primary text-primary-foreground">
          <Boxes class="size-5" />
        </span>
        <div>
          <div class="text-lg font-semibold">Nginx WebUI</div>
          <div class="text-xs text-muted-foreground">Nginx 管理控制台</div>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>登录</CardTitle>
          <CardDescription>使用系统账户继续访问管理控制台。</CardDescription>
        </CardHeader>
        <CardContent>
          <form class="space-y-4" @submit="submit">
            <div class="space-y-2">
              <Label for="username">用户名</Label>
              <div class="relative">
                <User class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="username"
                  v-model="username"
                  v-bind="usernameAttrs"
                  autocomplete="username"
                  class="pl-9"
                  placeholder="请输入用户名"
                  autofocus
                />
              </div>
              <p v-if="errors.username" class="text-sm text-destructive">{{ errors.username }}</p>
            </div>

            <div class="space-y-2">
              <Label for="password">密码</Label>
              <div class="relative">
                <LockKeyhole class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="password"
                  v-model="password"
                  v-bind="passwordAttrs"
                  type="password"
                  autocomplete="current-password"
                  class="pl-9"
                  placeholder="请输入密码"
                />
              </div>
              <p v-if="errors.password" class="text-sm text-destructive">{{ errors.password }}</p>
            </div>

            <Button type="submit" class="w-full" :disabled="loading">
              {{ loading ? '登录中…' : '登录' }}
            </Button>
          </form>
        </CardContent>
        <CardFooter class="border-t pt-5 text-xs text-muted-foreground">
          首次登录请使用默认管理员账户，并立即修改默认密码。
        </CardFooter>
      </Card>

      <p class="text-center text-xs text-muted-foreground">
        Power by numen06 ·
        <a class="hover:text-foreground hover:underline" href="https://gitee.com/numen06/nginx-webui" target="_blank" rel="noopener noreferrer">项目地址</a>
      </p>
    </div>
  </main>
</template>
