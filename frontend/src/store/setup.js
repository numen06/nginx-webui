import { defineStore } from 'pinia'
import { ref } from 'vue'
import { nginxApi } from '../api/nginx'

export const useSetupStore = defineStore('setup', () => {
  const showSetupWizard = ref(false)
  const hasCheckedSetup = ref(false)
  const setupStatus = ref(null)

  const checkSetupStatus = async (force = false) => {
    // 如果已经检查过且不强制，不再重复检查
    if (hasCheckedSetup.value && !force) {
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

      // 如果没有已编译的nginx，则显示引导页面
      // 如果有默认压缩包，可以直接使用；如果没有，用户需要上传或下载
      if (data && !data.has_compiled_nginx) {
        console.log('[SetupStore] 需要显示引导页面:', {
          has_compiled_nginx: data.has_compiled_nginx,
          has_default_tar: data.has_default_tar
        })
        showSetupWizard.value = true
      } else {
        console.log('[SetupStore] 不需要显示引导页面:', {
          has_compiled_nginx: data?.has_compiled_nginx,
          has_default_tar: data?.has_default_tar
        })
        // 如果nginx已经初始化，隐藏向导
        if (data && data.has_compiled_nginx) {
          showSetupWizard.value = false
        }
      }

      hasCheckedSetup.value = true
      return data
    } catch (error) {
      console.error('[SetupStore] 检查设置状态失败:', error)
      // 如果检查失败（比如404），说明nginx未初始化，显示引导页面
      // 只有在明确知道nginx已初始化时才不显示
      if (error.response?.status === 404 || error.detail?.includes('未找到')) {
        console.log('[SetupStore] 检测到nginx未初始化，显示引导页面')
        showSetupWizard.value = true
      }
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

