<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useAuthStore } from './store/auth'

const authStore = useAuthStore()

onMounted(() => {
  // 尝试从本地存储恢复登录状态
  const token = localStorage.getItem('token')
  if (token) {
    authStore.setToken(token)
  }
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

#app {
  width: 100%;
  height: 100vh;
  background-color: var(--bg-primary);
}
</style>

