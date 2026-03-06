import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { usePagedApiList } from './usePagedApiList'

const flush = async () => {
  await Promise.resolve()
  await nextTick()
}

describe('usePagedApiList', () => {
  it('loads paged rows and exposes pagination state', async () => {
    const fetchPage = vi.fn(async ({ page, pageSize }) => ({
      data: {
        items: [{ id: page * 10 + 1 }],
        total: 23,
        total_pages: Math.ceil(23 / pageSize)
      }
    }))

    const list = usePagedApiList({
      pageSize: 10,
      fetchPage,
      errorMessage: '加载失败'
    })

    await list.load()
    await flush()

    expect(fetchPage).toHaveBeenCalledWith({ page: 1, pageSize: 10 })
    expect(list.rows.value).toEqual([{ id: 11 }])
    expect(list.total.value).toBe(23)
    expect(list.totalPages.value).toBe(3)

    await list.nextPage()
    await flush()

    expect(fetchPage).toHaveBeenLastCalledWith({ page: 2, pageSize: 10 })
    expect(list.page.value).toBe(2)
  })

  it('resets overflowing page back into valid range', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce({
        data: {
          items: [],
          total: 5,
          total_pages: 1
        }
      })
      .mockResolvedValueOnce({
        data: {
          items: [{ id: 1 }],
          total: 5,
          total_pages: 1
        }
      })

    const list = usePagedApiList({
      pageSize: 10,
      fetchPage,
      errorMessage: '加载失败'
    })

    list.page.value = 3
    await list.load()
    await flush()

    expect(list.page.value).toBe(1)
    expect(fetchPage).toHaveBeenCalledTimes(2)
    expect(list.rows.value).toEqual([{ id: 1 }])
  })
})
