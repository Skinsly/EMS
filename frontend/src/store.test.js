import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './store'

describe('auth store session sync', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('persists auth and project fields into session storage', () => {
    const store = useAuthStore()

    store.setAuth('tester', 'token-123')
    store.setProject({ id: 7, name: '工程A' })

    expect(store.username).toBe('tester')
    expect(store.token).toBe('token-123')
    expect(store.projectId).toBe('7')
    expect(store.projectName).toBe('工程A')
    expect(sessionStorage.getItem('username')).toBe('tester')
    expect(sessionStorage.getItem('token')).toBe('token-123')
    expect(sessionStorage.getItem('projectId')).toBe('7')
    expect(sessionStorage.getItem('projectName')).toBe('工程A')
  })

  it('clears session-backed state on logout', () => {
    const store = useAuthStore()

    store.setAuth('tester', 'token-123')
    store.setProject({ id: 7, name: '工程A' })
    store.logout()

    expect(store.username).toBe('')
    expect(store.token).toBe('')
    expect(store.projectId).toBe('')
    expect(store.projectName).toBe('')
    expect(sessionStorage.getItem('username')).toBeNull()
    expect(sessionStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('projectId')).toBeNull()
    expect(sessionStorage.getItem('projectName')).toBeNull()
  })
})
