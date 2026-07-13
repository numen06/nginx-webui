import { defineStore } from 'pinia'
import { ref } from 'vue'
import { nginxApi } from '@/api/nginx'

export interface SetupStatus {
  has_compiled_nginx: boolean
  has_default_tar: boolean
  [key: string]: unknown
}

let setupRequest: Promise<SetupStatus | null> | null = null

export const useSetupStore = defineStore('setup', () => {
  const showSetupWizard = ref(false)
  const hasCheckedSetup = ref(false)
  const setupStatus = ref<SetupStatus | null>(null)

  async function checkSetupStatus(force = false): Promise<SetupStatus | null> {
    if (hasCheckedSetup.value && !force) return setupStatus.value
    if (setupRequest) return setupRequest

    setupRequest = nginxApi.checkSetupStatus()
      .then((response: SetupStatus) => {
        setupStatus.value = response
        showSetupWizard.value = !response.has_compiled_nginx
        hasCheckedSetup.value = true
        return response
      })
      .catch(() => {
        hasCheckedSetup.value = true
        return null
      })
      .finally(() => { setupRequest = null })
    return setupRequest
  }

  function markUnavailable() {
    setupStatus.value = setupStatus.value
      ? { ...setupStatus.value, has_compiled_nginx: false }
      : { has_compiled_nginx: false, has_default_tar: false }
    hasCheckedSetup.value = true
    showSetupWizard.value = true
  }

  function setShowSetupWizard(value: boolean) {
    showSetupWizard.value = value
  }

  function resetSetupCheck() {
    hasCheckedSetup.value = false
    setupStatus.value = null
  }

  return {
    showSetupWizard,
    hasCheckedSetup,
    setupStatus,
    checkSetupStatus,
    markUnavailable,
    setShowSetupWizard,
    resetSetupCheck,
  }
})
