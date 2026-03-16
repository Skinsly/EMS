import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useMachineLedgerPhotos } from './useMachineLedgerPhotos'

describe('useMachineLedgerPhotos', () => {
  beforeEach(() => {
    global.URL.createObjectURL = vi.fn(() => 'blob:test')
    global.URL.revokeObjectURL = vi.fn()
  })

  it('adds native photo files and exposes preview urls', () => {
    const api = { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
    const photos = useMachineLedgerPhotos({ api })
    const file = new File(['x'], 'a.png', { type: 'image/png' })

    photos.onNativePhotoChange({ target: { files: [file], value: 'x' } })

    expect(photos.photoFileList.value).toHaveLength(1)
    expect(photos.photoPreviewUrls.value).toEqual(['blob:test'])
  })

  it('deletes removed existing attachments', async () => {
    const api = { get: vi.fn(), post: vi.fn(), delete: vi.fn().mockResolvedValue({}) }
    const photos = useMachineLedgerPhotos({ api })
    photos.originalPhotoIds.value = [1, 2]
    photos.photoFileList.value = [{ uid: 'existing-0-2', id: 2, previewUrl: 'blob:test' }]

    await photos.removeDroppedExistingPhotos()

    expect(api.delete).toHaveBeenCalledTimes(1)
    expect(api.delete).toHaveBeenCalledWith('/attachments/1')
  })

  it('uploads new raw files only', async () => {
    const api = { get: vi.fn(), post: vi.fn().mockResolvedValue({}), delete: vi.fn() }
    const photos = useMachineLedgerPhotos({ api })
    const file = new File(['x'], 'a.png', { type: 'image/png' })
    photos.photoFileList.value = [{ raw: file }, { id: 2, previewUrl: 'blob:test' }]

    await photos.uploadNewPhotos(6)

    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post.mock.calls[0][0]).toContain('/attachments/upload?order_type=machine_ledger&order_id=6')
  })
})
