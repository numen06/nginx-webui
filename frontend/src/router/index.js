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
        path: 'profile',
        name: 'Profile',
        component: () => import('../views/Profile.vue'),
        meta: { title: '用户中心' }
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
  
  // 检查是否是默认密码，如果是且不是访问用户中心页面，则跳转到用户中心
  if (to.meta.requiresAuth && authStore.isAuthenticated && to.path !== '/profile') {
    // 如果用户信息中没有is_default_password字段，需要获取用户信息
    if (!authStore.user || authStore.user.is_default_password === undefined) {
      try {
        const { authApi } = await import('../api/auth')
        const userInfo = await authApi.getCurrentUser()
        authStore.setUser(userInfo.user)
        
        // 获取用户信息后，如果是默认密码，跳转到用户中心
        if (userInfo.user?.is_default_password === true) {
          next('/profile')
          return
        }
      } catch (error) {
        console.error('[Router] 获取用户信息失败:', error)
        // 如果获取失败，继续导航
      }
    } else {
      // 如果用户信息已存在，直接检查
      if (authStore.user?.is_default_password === true) {
        next('/profile')
        return
      }
    }
  }
  
  next()
})

export default router

