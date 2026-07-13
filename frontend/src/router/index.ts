import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/store/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    requiresAuth?: boolean
    requiresAdmin?: boolean
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '仪表盘' } },
      { path: 'config', name: 'Config', component: () => import('@/views/Config.vue'), meta: { title: '配置管理' } },
      { path: 'dynamic-services', name: 'DynamicServices', component: () => import('@/views/DynamicServices.vue'), meta: { title: '动态服务' } },
      { path: 'git-sync', name: 'GitSync', component: () => import('@/views/GitSync.vue'), meta: { title: 'Git 配置同步' } },
      { path: 'logs', name: 'Logs', component: () => import('@/views/Logs.vue'), meta: { title: '日志查看' } },
      { path: 'files', name: 'Files', component: () => import('@/views/Files.vue'), meta: { title: '文件管理' } },
      { path: 'static-package', name: 'StaticPackage', component: () => import('@/views/StaticPackage.vue'), meta: { title: '静态资源包管理' } },
      { path: 'certificates', name: 'Certificates', component: () => import('@/views/Certificates.vue'), meta: { title: '证书管理' } },
      { path: 'audit', name: 'Audit', component: () => import('@/views/Audit.vue'), meta: { title: '操作日志' } },
      { path: 'nginx', name: 'Nginx', component: () => import('@/views/Nginx.vue'), meta: { title: 'Nginx 管理' } },
      { path: 'users', name: 'Users', component: () => import('@/views/Users.vue'), meta: { title: '用户管理', requiresAdmin: true } },
      { path: 'profile', name: 'Profile', component: () => import('@/views/Profile.vue'), meta: { title: '用户中心' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth)

  if (requiresAuth && !authStore.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  if (authStore.isAuthenticated && (!authStore.user || requiresAuth)) {
    const user = await authStore.ensureUser()
    if (!user && requiresAuth) return { path: '/login' }
  }

  if (to.path === '/login' && authStore.isAuthenticated) return '/dashboard'

  if (
    requiresAuth
    && authStore.user?.is_default_password
    && to.path !== '/profile'
  ) {
    return '/profile'
  }

  if (to.meta.requiresAdmin && !authStore.isAdmin) return '/dashboard'
  return true
})

router.afterEach(to => {
  document.title = to.meta.title ? `${to.meta.title} · Nginx WebUI` : 'Nginx WebUI'
})

export default router
