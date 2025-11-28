import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../store/auth'
import { useSetupStore } from '../store/setup'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('../layouts/MainLayout.vue'),
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '仪表盘' }
      },
      {
        path: 'config',
        name: 'Config',
        component: () => import('../views/Config.vue'),
        meta: { title: '配置管理' }
      },
      {
        path: 'git-sync',
        name: 'GitSync',
        component: () => import('../views/GitSync.vue'),
        meta: { title: 'Git 配置同步' }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('../views/Logs.vue'),
        meta: { title: '日志查看' }
      },
      {
        path: 'files',
        name: 'Files',
        component: () => import('../views/Files.vue'),
        meta: { title: '文件管理' }
      },
      {
        path: 'static-package',
        name: 'StaticPackage',
        component: () => import('../views/StaticPackage.vue'),
        meta: { title: '静态资源包管理' }
      },
      {
        path: 'certificates',
        name: 'Certificates',
        component: () => import('../views/Certificates.vue'),
        meta: { title: '证书管理' }
      },
      {
        path: 'audit',
        name: 'Audit',
        component: () => import('../views/Audit.vue'),
        meta: { title: '操作日志' }
      },
      {
        path: 'nginx',
        name: 'Nginx',
        component: () => import('../views/Nginx.vue'),
        meta: { title: 'Nginx 管理' }
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('../views/Users.vue'),
        meta: { title: '用户管理' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()
  const setupStore = useSetupStore()
  
  // 检查认证
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next('/login')
    return
  }
  
  if (to.path === '/login' && authStore.isAuthenticated) {
    next('/')
    return
  }
  
  // 如果需要认证的页面，提前检查nginx设置状态
  // 这样可以在其他API调用之前就显示引导页面
  if (to.meta.requiresAuth && authStore.isAuthenticated && !setupStore.hasCheckedSetup) {
    console.log('[Router] 在路由守卫中检查nginx设置状态')
    try {
      await setupStore.checkSetupStatus()
    } catch (error) {
      console.error('[Router] 检查设置状态失败:', error)
      // 即使检查失败也继续导航
    }
  }
  
  next()
})

export default router

