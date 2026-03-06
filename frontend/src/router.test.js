import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './store'
import { resolveRouteGuard } from './router'

describe('router auth guard', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setActivePinia(createPinia())
  })

  it('redirects unauthenticated users to login', () => {
    expect(resolveRouteGuard({ path: '/materials' })).toBe('/login')
  })

  it('redirects authenticated users away from login', () => {
    const auth = useAuthStore()
    auth.setAuth('tester', 'token-123')

    expect(resolveRouteGuard({ path: '/login' })).toBe('/projects')
  })

  it('requires a selected project before entering project-scoped pages', () => {
    const auth = useAuthStore()
    auth.setAuth('tester', 'token-123')

    expect(resolveRouteGuard({ path: '/materials' })).toBe('/projects')
  })

  it('allows project-scoped pages when auth and project are present', () => {
    const auth = useAuthStore()
    auth.setAuth('tester', 'token-123')
    auth.setProject({ id: 3, name: '工程A' })

    expect(resolveRouteGuard({ path: '/materials' })).toBe(true)
  })
})
