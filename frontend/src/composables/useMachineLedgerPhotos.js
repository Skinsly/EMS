import { computed, ref } from 'vue'

export const useMachineLedgerPhotos = ({ api }) => {
  const photoFileList = ref([])
  const originalPhotoIds = ref([])
  const albumInputRef = ref(null)
  const detailPhotos = ref([])
  const detailPhotoUrls = ref([])
  const photoPreviewUrls = computed(() => photoFileList.value.map((item) => item.previewUrl).filter(Boolean))

  const revokeObjectUrl = (url) => {
    if (url?.startsWith('blob:')) URL.revokeObjectURL(url)
  }

  const clearPhotoFiles = () => {
    photoFileList.value.forEach((item) => revokeObjectUrl(item.previewUrl))
    photoFileList.value = []
    originalPhotoIds.value = []
  }

  const clearDetailPhotos = () => {
    detailPhotos.value.forEach((item) => revokeObjectUrl(item.previewUrl))
    detailPhotos.value = []
    detailPhotoUrls.value = []
  }

  const loadAttachmentPreviewUrl = async (id) => {
    const { data } = await api.get(`/attachments/${id}/download`, { responseType: 'blob' })
    return URL.createObjectURL(data)
  }

  const openPhotoPicker = () => {
    albumInputRef.value?.click()
  }

  const onNativePhotoChange = (event) => {
    const files = Array.from(event.target.files || [])
    const remain = Math.max(0, 12 - photoFileList.value.length)
    const picked = files.slice(0, remain).map((file, idx) => ({
      uid: `native-${Date.now()}-${idx}`,
      name: file.name,
      status: 'ready',
      raw: file,
      previewUrl: URL.createObjectURL(file)
    }))
    photoFileList.value = [...photoFileList.value, ...picked]
    event.target.value = ''
  }

  const removePhoto = (uid) => {
    const target = photoFileList.value.find((item) => item.uid === uid)
    if (target) revokeObjectUrl(target.previewUrl)
    photoFileList.value = photoFileList.value.filter((item) => item.uid !== uid)
  }

  const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms))

  const uploadPhotoWithRetry = async (rowId, rawFile, maxAttempts = 2) => {
    let lastError = null
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const fd = new FormData()
        fd.append('file', rawFile)
        await api.post(`/attachments/upload?order_type=machine_ledger&order_id=${rowId}`, fd)
        return
      } catch (err) {
        lastError = err
        if (attempt < maxAttempts) {
          await sleep(250)
        }
      }
    }
    throw lastError
  }

  const loadEditPhotos = async (editingId) => {
    const { data } = await api.get(`/attachments?order_type=machine_ledger&order_id=${editingId}`)
    originalPhotoIds.value = (data || []).map((item) => Number(item.id)).filter((id) => Number.isFinite(id) && id > 0)
    const files = await Promise.all(
      (data || []).map(async (item, idx) => ({
        uid: `existing-${idx}-${item.id}`,
        id: Number(item.id),
        name: item.filename,
        status: 'success',
        previewUrl: await loadAttachmentPreviewUrl(item.id)
      }))
    )
    photoFileList.value = files
  }

  const removeDroppedExistingPhotos = async () => {
    const keepExistingIds = new Set(
      photoFileList.value
        .filter((item) => String(item.uid || '').startsWith('existing-'))
        .map((item) => Number(item.id))
        .filter((id) => Number.isFinite(id) && id > 0)
    )
    for (const id of originalPhotoIds.value) {
      if (!keepExistingIds.has(id)) {
        await api.delete(`/attachments/${id}`)
      }
    }
  }

  const uploadNewPhotos = async (rowId) => {
    for (const item of photoFileList.value) {
      if (!item.raw) continue
      await uploadPhotoWithRetry(rowId, item.raw, 2)
    }
  }

  const loadDetailPhotoSet = async (detailId, detailRequest, token) => {
    clearDetailPhotos()
    const { data } = await api.get(`/attachments?order_type=machine_ledger&order_id=${detailId}`)
    if (!detailRequest.isLatest(token)) return
    const photos = await Promise.all((data || []).map(async (item) => ({ ...item, previewUrl: await loadAttachmentPreviewUrl(item.id) })))
    if (!detailRequest.isLatest(token)) {
      photos.forEach((item) => revokeObjectUrl(item.previewUrl))
      return
    }
    detailPhotos.value = photos
    detailPhotoUrls.value = photos.map((item) => item.previewUrl)
  }

  return {
    albumInputRef,
    photoFileList,
    originalPhotoIds,
    photoPreviewUrls,
    detailPhotos,
    detailPhotoUrls,
    clearPhotoFiles,
    clearDetailPhotos,
    openPhotoPicker,
    onNativePhotoChange,
    removePhoto,
    uploadNewPhotos,
    loadEditPhotos,
    removeDroppedExistingPhotos,
    loadDetailPhotoSet
  }
}
