import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ECharts from 'vue-echarts'
import App from './App.vue'
import router from './router'
import { installAppCompat } from '@/components/app/compat'
import { useAuthStore } from '@/store/auth'
import { useSetupStore } from '@/store/setup'
import { loadingDirective } from '@/directives/loading'
import './styles/theme.css'

const app = createApp(App)
const pinia = createPinia()

app.component('VChart', ECharts)
installAppCompat(app)
app.directive('loading', loadingDirective)
app.use(pinia)
app.use(router)

window.addEventListener('auth:unauthorized', () => {
  useAuthStore(pinia).logout()
  if (router.currentRoute.value.path !== '/login') void router.replace('/login')
})
window.addEventListener('nginx:unavailable', () => {
  useSetupStore(pinia).markUnavailable()
})

app.mount('#app')
