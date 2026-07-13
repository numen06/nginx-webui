import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authApi } from '@/api/auth'
import { useAuthStore } from './auth'

vi.mock('@/api/auth', () => ({
  authApi: { login: vi.fn(), getCurrentUser: vi.fn() },
}))

describe('auth store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('derives administrator permission from the current user', () => {
    const store = useAuthStore()
    store.setUser({ id: 1, username: 'admin', is_active: true, is_admin: true, created_at: null })
    expect(store.isAdmin).toBe(true)
  })

  it('clears a rejected session', async () => {
    localStorage.setItem('token', 'expired')
    setActivePinia(createPinia())
    vi.mocked(authApi.getCurrentUser).mockRejectedValue(new Error('401'))
    const store = useAuthStore()
    expect(await store.ensureUser()).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('token')).toBeNull()
  })
})
