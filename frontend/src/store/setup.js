import { defineStore } from 'pinia'
import { ref } from 'vue'
import { nginxApi } from '../api/nginx'

export const useSetupStore = defineStore('setup', () => {
  const showSetupWizard = ref(false)
  const hasCheckedSetup = ref(false)
  const setupStatus = ref(null)

  const checkSetupStatus = async () => {
    // 如果已经检查过，不再重复检查
    if (hasCheckedSetup.value) {
      return setupStatus.value
    }

    try {
      console.log('[SetupStore] 检查Nginx设置状态...')
      const response = await nginxApi.checkSetupStatus()
      console.log('[SetupStore] 设置状态响应:', response)

      // API拦截器返回的是 response.data
      let data = response
      if (response && typeof response === 'object' && 'data' in response) {
        data = response.data
      }

      setupStatus.value = data

      // 如果没有已编译的nginx，且有默认压缩包，则显示引导页面
      if (data && !data.has_compiled_nginx && data.has_default_tar) {
        console.log('[SetupStore] 需要显示引导页面')
        showSetupWizard.value = true
      } else {
        console.log('[SetupStore] 不需要显示引导页面:', {
          has_compiled_nginx: data?.has_compiled_nginx,
          has_default_tar: data?.has_default_tar
        })
      }

      hasCheckedSetup.value = true
      return data
    } catch (error) {
      console.error('[SetupStore] 检查设置状态失败:', error)
      // 检查失败时不显示引导页面，让用户正常使用
      hasCheckedSetup.value = true
      return null
    }
  }

  const setShowSetupWizard = (value) => {
    showSetupWizard.value = value
  }

  const resetSetupCheck = () => {
    hasCheckedSetup.value = false
    setupStatus.value = null
  }

  return {
    showSetupWizard,
    hasCheckedSetup,
    setupStatus,
    checkSetupStatus,
    setShowSetupWizard,
    resetSetupCheck
  }
})

