<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  Activity,
  BadgeCheck,
  Boxes,
  ChevronDown,
  FileArchive,
  FileCode2,
  FileText,
  FolderTree,
  Gauge,
  GitBranch,
  Info,
  LogOut,
  Network,
  RefreshCw,
  ScrollText,
  Settings2,
  ShieldCheck,
  User,
  Users,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { ElMessage } from '@/lib/feedback'
import { useAuthStore } from '@/store/auth'
import { useSetupStore } from '@/store/setup'
import { systemApi } from '@/api/system'
import NginxSetupWizard from '@/components/NginxSetupWizard.vue'

interface NavigationItem {
  label: string
  path: string
  icon: typeof Gauge
  admin?: boolean
}

interface NavigationGroup {
  label: string
  items: NavigationItem[]
}

interface UpdateStatus {
  hasUpdate: boolean
  latestVersion: string | null
  releaseUrl: string | null
  releaseName: string | null
  currentVersion: string | null
  releaseBody: string | null
  checkSuccess: boolean
  checkMessage: string
}

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const setupStore = useSetupStore()
const versionDialogVisible = ref(false)
const checkLoading = ref(false)
const systemVersion = ref<string | null>(null)
const updateStatus = ref<UpdateStatus>({
  hasUpdate: false,
  latestVersion: null,
  releaseUrl: null,
  releaseName: null,
  currentVersion: null,
  releaseBody: null,
  checkSuccess: true,
  checkMessage: '',
})

const navigation: NavigationGroup[] = [
  { label: '概览', items: [{ label: '仪表盘', path: '/dashboard', icon: Gauge }] },
  {
    label: '配置',
    items: [
      { label: '配置管理', path: '/config', icon: FileCode2 },
      { label: '动态服务', path: '/dynamic-services', icon: Network },
      { label: 'Git 配置同步', path: '/git-sync', icon: GitBranch },
    ],
  },
  {
    label: '运维',
    items: [
      { label: 'Nginx 管理', path: '/nginx', icon: Settings2 },
      { label: '证书管理', path: '/certificates', icon: ShieldCheck },
      { label: '文件管理', path: '/files', icon: FolderTree },
      { label: '静态资源包', path: '/static-package', icon: FileArchive },
    ],
  },
  {
    label: '可观测性',
    items: [
      { label: '日志查看', path: '/logs', icon: FileText },
      { label: '操作日志', path: '/audit', icon: ScrollText },
    ],
  },
  {
    label: '系统',
    items: [{ label: '用户管理', path: '/users', icon: Users, admin: true }],
  },
]

const visibleNavigation = computed(() => navigation
  .map(group => ({
    ...group,
    items: group.items.filter(item => !item.admin || authStore.isAdmin),
  }))
  .filter(group => group.items.length))

const currentTitle = computed(() => String(route.meta.title || 'Nginx WebUI'))
const userInitial = computed(() => (authStore.username || 'U').slice(0, 1).toUpperCase())
const displayCurrentVersion = computed(() => updateStatus.value.currentVersion || systemVersion.value || '—')
const showSetupWizard = computed({
  get: () => setupStore.showSetupWizard,
  set: value => setupStore.setShowSetupWizard(value),
})

function handleLogout() {
  authStore.logout()
  ElMessage.success('已退出登录')
  void router.replace('/login')
}

async function loadSystemVersion() {
  try {
    const response = await systemApi.getVersion()
    systemVersion.value = response.version || null
  } catch {
    systemVersion.value = null
  }
}

async function loadUpdateStatus(showLoading = false) {
  if (showLoading) checkLoading.value = true
  try {
    const response = await systemApi.checkUpdate()
    updateStatus.value = {
      hasUpdate: Boolean(response.has_update),
      latestVersion: response.latest_version || null,
      releaseUrl: response.release_url || null,
      releaseName: response.release_name || null,
      currentVersion: response.current_version || null,
      releaseBody: response.release_body || null,
      checkSuccess: Boolean(response.success),
      checkMessage: response.message || '',
    }
  } catch (error) {
    updateStatus.value.checkSuccess = false
    updateStatus.value.checkMessage = error instanceof Error ? error.message : '检查更新失败'
  } finally {
    checkLoading.value = false
  }
}

async function openVersionDialog() {
  versionDialogVisible.value = true
  await loadUpdateStatus(true)
}

function openReleasePage() {
  if (updateStatus.value.releaseUrl) {
    window.open(updateStatus.value.releaseUrl, '_blank', 'noopener,noreferrer')
  }
}

function handleSetupComplete() {
  setupStore.setShowSetupWizard(false)
  ElMessage.success('Nginx 设置完成，系统已就绪')
}

onMounted(() => {
  void authStore.ensureUser()
  void setupStore.checkSetupStatus()
  void loadSystemVersion()
  void loadUpdateStatus()
})
</script>

<template>
  <SidebarProvider>
    <Sidebar collapsible="icon">
      <SidebarHeader class="border-b border-sidebar-border p-3">
        <RouterLink to="/dashboard" class="flex items-center gap-3 overflow-hidden rounded-md px-1 py-1.5">
          <span class="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Boxes class="size-4" />
          </span>
          <div class="min-w-0 leading-tight group-data-[collapsible=icon]:hidden">
            <div class="truncate text-sm font-semibold">Nginx WebUI</div>
            <div class="truncate text-xs text-muted-foreground">管理控制台</div>
          </div>
        </RouterLink>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup v-for="group in visibleNavigation" :key="group.label">
          <SidebarGroupLabel>{{ group.label }}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem v-for="item in group.items" :key="item.path">
                <SidebarMenuButton
                  as-child
                  :is-active="route.path === item.path"
                  :tooltip="item.label"
                >
                  <RouterLink :to="item.path">
                    <component :is="item.icon" />
                    <span>{{ item.label }}</span>
                  </RouterLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter class="border-t border-sidebar-border p-2">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton tooltip="版本与更新" @click="openVersionDialog">
              <Info />
              <span class="truncate">版本 {{ systemVersion || '—' }}</span>
              <span v-if="updateStatus.hasUpdate" class="ml-auto size-2 rounded-full bg-amber-400" />
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <a
          href="https://gitee.com/numen06/nginx-webui"
          target="_blank"
          rel="noopener noreferrer"
          class="px-2 pb-1 text-[11px] text-muted-foreground hover:text-foreground group-data-[collapsible=icon]:hidden"
        >
          Power by numen06
        </a>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>

    <SidebarInset class="min-w-0 bg-background">
      <header class="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <SidebarTrigger />
        <Separator orientation="vertical" class="h-5" />
        <h1 class="truncate text-sm font-medium md:text-base">{{ currentTitle }}</h1>
        <div class="ml-auto flex items-center gap-2">
          <Badge v-if="authStore.isAdmin" variant="secondary" class="hidden md:inline-flex">
            <BadgeCheck class="mr-1 size-3" />超级管理员
          </Badge>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button variant="ghost" class="h-10 gap-2 px-2 sm:px-3">
                <span class="grid size-7 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                  {{ userInitial }}
                </span>
                <span class="hidden max-w-32 truncate text-sm sm:inline">{{ authStore.username || '用户' }}</span>
                <ChevronDown class="hidden size-3.5 text-muted-foreground sm:block" />
                <span class="sr-only">打开用户菜单</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" class="w-56">
              <DropdownMenuLabel>
                <div>{{ authStore.username }}</div>
                <div class="text-xs font-normal text-muted-foreground">
                  {{ authStore.isAdmin ? '超级管理员' : '普通用户' }}
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem @click="router.push('/profile')">
                <User class="size-4" /> 用户中心
              </DropdownMenuItem>
              <DropdownMenuItem @click="handleLogout">
                <LogOut class="size-4" /> 退出登录
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>
      <main class="min-w-0 flex-1 overflow-x-hidden">
        <RouterView />
      </main>
    </SidebarInset>
  </SidebarProvider>

  <NginxSetupWizard v-model="showSetupWizard" @complete="handleSetupComplete" />

  <Dialog v-model:open="versionDialogVisible">
    <DialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-xl">
      <DialogHeader>
        <DialogTitle>版本与更新</DialogTitle>
        <DialogDescription>查看当前运行版本和最新发行版。</DialogDescription>
      </DialogHeader>
      <div class="grid gap-3 rounded-lg border p-4 text-sm sm:grid-cols-[9rem_1fr]">
        <span class="text-muted-foreground">当前运行版本</span><span>{{ displayCurrentVersion }}</span>
        <span class="text-muted-foreground">Gitee 最新版本</span><span>{{ updateStatus.latestVersion || '—' }}</span>
        <span v-if="updateStatus.releaseName" class="text-muted-foreground">Release 名称</span><span v-if="updateStatus.releaseName">{{ updateStatus.releaseName }}</span>
      </div>
      <div v-if="!updateStatus.checkSuccess" class="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-red-200">
        {{ updateStatus.checkMessage || '检查更新失败' }}
      </div>
      <div v-else-if="updateStatus.hasUpdate" class="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">
        发现新版本，请按项目说明升级。
      </div>
      <div v-if="updateStatus.releaseBody" class="space-y-2">
        <h3 class="text-sm font-medium">发行说明</h3>
        <pre class="max-h-72 whitespace-pre-wrap rounded-lg bg-muted p-3 text-xs text-muted-foreground">{{ updateStatus.releaseBody }}</pre>
      </div>
      <DialogFooter>
        <Button variant="secondary" :disabled="checkLoading" @click="loadUpdateStatus(true)">
          <RefreshCw :class="['size-4', { 'animate-spin': checkLoading }]" />重新检查
        </Button>
        <Button
          :disabled="!updateStatus.releaseUrl"
          @click="openReleasePage"
        >
          在 Gitee 查看
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
