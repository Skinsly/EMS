import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../store'
import { createProjectsActions } from './projectsActions'

describe('ProjectsPage actions', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('persists selected project and navigates into project workspace', () => {
    const auth = useAuthStore()
    const router = { push: vi.fn() }
    const message = { success: vi.fn() }
    const actions = createProjectsActions({ auth, router, message })

    actions.enterProject({ id: 9, name: '测试工程A' })

    expect(auth.projectId).toBe('9')
    expect(auth.projectName).toBe('测试工程A')
    expect(sessionStorage.getItem('projectId')).toBe('9')
    expect(sessionStorage.getItem('projectName')).toBe('测试工程A')
    expect(message.success).toHaveBeenCalledWith('已切换到工程: 测试工程A')
    expect(router.push).toHaveBeenCalledWith('/construction-logs')
  })

  it('clears auth state and redirects to login on logout', () => {
    const auth = useAuthStore()
    auth.setAuth('tester', 'token-123')
    auth.setProject({ id: 9, name: '测试工程A' })

    const router = { push: vi.fn() }
    const message = { success: vi.fn() }
    const actions = createProjectsActions({ auth, router, message })

    actions.logout()

    expect(auth.username).toBe('')
    expect(auth.token).toBe('')
    expect(auth.projectId).toBe('')
    expect(auth.projectName).toBe('')
    expect(sessionStorage.getItem('token')).toBeNull()
    expect(sessionStorage.getItem('projectId')).toBeNull()
    expect(router.push).toHaveBeenCalledWith('/login')
  })

  it('clears active project when the deleted ids include current project', () => {
    const auth = useAuthStore()
    auth.setAuth('tester', 'token-123')
    auth.setProject({ id: 9, name: '测试工程A' })

    const router = { push: vi.fn() }
    const message = { success: vi.fn() }
    const actions = createProjectsActions({ auth, router, message })

    actions.clearDeletedProjects([5, 9])

    expect(auth.projectId).toBe('')
    expect(auth.projectName).toBe('')
    expect(sessionStorage.getItem('projectId')).toBeNull()
    expect(sessionStorage.getItem('projectName')).toBeNull()
  })
})
