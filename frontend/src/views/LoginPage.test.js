import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'
import { useAuthStore } from '../store'
import { createLoginActions } from './loginActions'

describe('LoginPage actions', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('stores auth state and redirects on successful login', async () => {
    const auth = useAuthStore()
    const router = { push: vi.fn() }
    const message = { success: vi.fn() }
    const showLoginError = vi.fn()
    const actions = createLoginActions({ auth, router, message, showLoginError })

    const initialized = ref(true)
    const username = ref('input-user')
    const password = ref('Pass1234')

    const result = await actions.submit({
      initialized,
      username,
      password,
      loginApi: vi.fn().mockResolvedValue({
        data: { username: 'server-user', access_token: 'token-123' }
      })
    })

    expect(result.status).toBe('ok')
    expect(auth.username).toBe('server-user')
    expect(auth.token).toBe('token-123')
    expect(sessionStorage.getItem('username')).toBe('server-user')
    expect(sessionStorage.getItem('token')).toBe('token-123')
    expect(message.success).toHaveBeenCalledWith('登录成功')
    expect(router.push).toHaveBeenCalledWith('/projects')
    expect(showLoginError).not.toHaveBeenCalled()
  })

  it('returns bootstrap-required result when backend reports uninitialized system', async () => {
    const auth = useAuthStore()
    const router = { push: vi.fn() }
    const message = { success: vi.fn() }
    const showLoginError = vi.fn()
    const actions = createLoginActions({ auth, router, message, showLoginError })

    const initialized = ref(true)
    const username = ref('input-user')
    const password = ref('Pass1234')

    const result = await actions.submit({
      initialized,
      username,
      password,
      loginApi: vi.fn().mockRejectedValue({
        response: { data: { detail: '系统未初始化，请先创建管理员账号' } }
      })
    })

    expect(result.status).toBe('needs-init')
    result.onHandled?.()
    expect(showLoginError).toHaveBeenCalledWith('系统未初始化，请先设置账号密码')
    expect(auth.token).toBe('')
    expect(router.push).not.toHaveBeenCalled()
  })
})
