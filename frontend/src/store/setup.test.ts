import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nginxApi } from '@/api/nginx'
import { useSetupStore } from './setup'

vi.mock('@/api/nginx', () => ({
  nginxApi: { checkSetupStatus: vi.fn() },
}))

describe('setup store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('deduplicates concurrent setup checks', async () => {
    let resolve!: (value: { has_compiled_nginx: boolean; has_default_tar: boolean }) => void
    vi.mocked(nginxApi.checkSetupStatus).mockReturnValue(new Promise(done => { resolve = done }))
    const store = useSetupStore()
    const first = store.checkSetupStatus()
    const second = store.checkSetupStatus()
    resolve({ has_compiled_nginx: true, has_default_tar: true })
    await Promise.all([first, second])
    expect(nginxApi.checkSetupStatus).toHaveBeenCalledTimes(1)
    expect(store.showSetupWizard).toBe(false)
  })

  it('shows the wizard only for an explicit unavailable state', () => {
    const store = useSetupStore()
    store.markUnavailable()
    expect(store.showSetupWizard).toBe(true)
    expect(store.setupStatus?.has_compiled_nginx).toBe(false)
  })
})
