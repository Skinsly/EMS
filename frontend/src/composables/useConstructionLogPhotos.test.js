import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useConstructionLogPhotos } from './useConstructionLogPhotos'

describe('useConstructionLogPhotos', () => {
  beforeEach(() => {
    global.URL.createObjectURL = vi.fn(() => 'blob:test')
    global.URL.revokeObjectURL = vi.fn()
  })

  it('filters non-image files and warns on invalid input', () => {
    const api = { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
    const notify = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
    const photos = useConstructionLogPhotos({ api, notify, maxPhotos: 3 })
    const img = new File(['x'], 'a.png', { type: 'image/png' })
    const txt = new File(['x'], 'a.txt', { type: 'text/plain' })

    photos.appendRawPhotoFiles([img, txt])

    expect(photos.photoFileList.value).toHaveLength(1)
    expect(notify.error).toHaveBeenCalledWith('仅支持图片文件')
  })

  it('prevents exceeding max photo count', () => {
    const api = { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
    const notify = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
    const photos = useConstructionLogPhotos({ api, notify, maxPhotos: 1 })
    const img1 = new File(['x'], 'a.png', { type: 'image/png' })
    const img2 = new File(['x'], 'b.png', { type: 'image/png' })

    photos.appendRawPhotoFiles([img1, img2])

    expect(photos.photoFileList.value).toHaveLength(1)
    expect(notify.warning).toHaveBeenCalled()
  })

  it('uploads all queued images and returns upload count', async () => {
    const api = { get: vi.fn(), post: vi.fn().mockResolvedValue({}), delete: vi.fn() }
    const notify = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
    const photos = useConstructionLogPhotos({ api, notify, maxPhotos: 3 })
    const img1 = new File(['x'], 'a.png', { type: 'image/png' })
    const img2 = new File(['x'], 'b.png', { type: 'image/png' })
    photos.photoFileList.value = [{ raw: img1 }, { raw: img2 }]

    const uploaded = await photos.uploadPhotosForLog(5)

    expect(uploaded).toBe(2)
    expect(api.post).toHaveBeenCalledTimes(2)
  })
})
