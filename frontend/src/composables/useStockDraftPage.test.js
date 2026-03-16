import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h } from 'vue'
import { useStockDraftPage } from './useStockDraftPage'

const routerReplace = vi.fn()
let routeLeaveGuard = null
const notifyApi = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn()
}))
const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/stock-manage', query: {} }),
  useRouter: () => ({ replace: routerReplace }),
  onBeforeRouteLeave: (guard) => {
    routeLeaveGuard = guard
  }
}))

vi.mock('../api', () => ({
  default: {
    get: apiMocks.get,
    put: apiMocks.put,
    post: apiMocks.post
  }
}))

vi.mock('../utils/notify', () => ({
  notify: notifyApi
}))

const flushPromises = async (times = 3) => {
  for (let index = 0; index < times; index += 1) {
    await Promise.resolve()
  }
}

const mountDraftComposable = async () => {
  let exposed = null
  const host = document.createElement('div')
  document.body.appendChild(host)

  const app = createApp({
    setup() {
      exposed = useStockDraftPage('in')
      return () => h('div')
    }
  })

  app.mount(host)
  await flushPromises()

  return {
    app,
    host,
    exposed
  }
}

describe('useStockDraftPage', () => {
  beforeEach(() => {
    routeLeaveGuard = null
    routerReplace.mockReset()
    apiMocks.get.mockReset()
    apiMocks.put.mockReset()
    apiMocks.post.mockReset()
    notifyApi.success.mockReset()
    notifyApi.error.mockReset()
    notifyApi.warning.mockReset()
    sessionStorage.clear()
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('aborts commit when forced draft save fails', async () => {
    apiMocks.get
      .mockResolvedValueOnce({ data: [{ id: 1, name: '钢筋', spec: 'HRB400' }] })
      .mockResolvedValueOnce({
        data: {
          items: [{ date: '2026-03-01', material_id: 1, qty: 2, remark: '待入账' }],
          updated_at: '2026-03-01T10:00:00'
        }
      })
    apiMocks.put.mockRejectedValue({ response: { data: { detail: '草稿保存失败-测试' } } })

    const { app, host, exposed } = await mountDraftComposable()

    await exposed.commitDraft()
    await flushPromises()

    expect(apiMocks.put).toHaveBeenCalledWith('/stock-drafts/in', [
      { date: '2026-03-01', material_id: 1, qty: 2, remark: '待入账' }
    ])
    expect(apiMocks.post).not.toHaveBeenCalled()
    expect(notifyApi.error).toHaveBeenCalled()
    expect(exposed.commitLoading.value).toBe(false)

    app.unmount()
    host.remove()
  })

  it('cancels route leave when forced save fails on dirty draft', async () => {
    apiMocks.get
      .mockResolvedValueOnce({ data: [{ id: 1, name: '钢筋', spec: 'HRB400' }] })
      .mockResolvedValueOnce({ data: { items: [], updated_at: '' } })
    apiMocks.put.mockRejectedValue({ response: { data: { detail: '草稿保存失败-离页' } } })

    const { app, host, exposed } = await mountDraftComposable()

    exposed.draftRow.value.date = '2026-03-01'
    exposed.draftRow.value.material_id = 1
    exposed.draftRow.value.qty = 3
    exposed.draftRow.value.remark = '新增草稿'
    exposed.confirmAddRow()
    await flushPromises()

    const next = vi.fn()
    await routeLeaveGuard({}, {}, next)

    expect(apiMocks.put).toHaveBeenCalled()
    expect(next).toHaveBeenCalledWith(false)

    app.unmount()
    host.remove()
  })
})
