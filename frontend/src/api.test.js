import { beforeEach, describe, expect, it } from 'vitest'
import { applyAuthHeaders } from './api'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './store'

describe('api auth headers', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setActivePinia(createPinia())
  })

  it('injects bearer token and project header from session-backed store', () => {
    const auth = useAuthStore()
    auth.setAuth('tester', 'token-123')
    auth.setProject({ id: 12, name: '工程A' })

    const config = applyAuthHeaders({ headers: {} })

    expect(config.headers.Authorization).toBe('Bearer token-123')
    expect(config.headers['X-Project-Id']).toBe('12')
  })

  it('keeps empty headers when no auth or project is selected', () => {
    const config = applyAuthHeaders({ headers: {} })

    expect(config.headers.Authorization).toBeUndefined()
    expect(config.headers['X-Project-Id']).toBeUndefined()
  })
})
