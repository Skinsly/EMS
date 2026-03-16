import { computed, ref } from 'vue'

export const useConstructionLogPhotos = ({ api, notify, maxPhotos }) => {
  const existingPhotos = ref([])
  const photoFileList = ref([])
  const albumInputRef = ref(null)
  const existingPhotoUrls = computed(() => existingPhotos.value.map((item) => item.previewUrl).filter(Boolean))
  const newPhotoUrls = computed(() => photoFileList.value.map((item) => item.previewUrl).filter(Boolean))

  const loadAttachmentPreviewUrl = async (attachmentId) => {
    const { data } = await api.get(`/attachments/${attachmentId}/download`, { responseType: 'blob' })
    return URL.createObjectURL(data)
  }

  const revokeObjectUrl = (url) => {
    if (url?.startsWith('blob:')) {
      URL.revokeObjectURL(url)
    }
  }

  const onPhotoExceed = () => {
    notify.warning('照片数量已达上限')
  }

  const appendRawPhotoFiles = (rawFiles) => {
    const files = Array.from(rawFiles || [])
    if (!files.length) return

    const imageFiles = files.filter((file) => (file?.type || '').startsWith('image/'))
    if (imageFiles.length !== files.length) {
      notify.error('仅支持图片文件')
    }
    if (!imageFiles.length) return

    const remain = Math.max(0, maxPhotos - existingPhotos.value.length)
    const available = Math.max(0, remain - photoFileList.value.length)
    if (!available) {
      notify.warning('照片数量已达上限')
      return
    }

    const accepted = imageFiles.slice(0, available)
    if (accepted.length < imageFiles.length) {
      notify.warning('照片数量已达上限')
    }

    const list = accepted.map((file, idx) => ({
      name: file.name,
      raw: file,
      uid: `native-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 8)}`,
      previewUrl: URL.createObjectURL(file)
    }))
    photoFileList.value = [...photoFileList.value, ...list]
  }

  const onNativePhotoPicked = (event) => {
    const input = event.target
    appendRawPhotoFiles(input?.files)
    if (input) {
      input.value = ''
    }
  }

  const openMobilePhotoPicker = () => {
    albumInputRef.value?.click()
  }

  const clearPhotoFiles = () => {
    photoFileList.value.forEach((item) => revokeObjectUrl(item?.previewUrl))
    photoFileList.value = []
  }

  const clearExistingPhotos = () => {
    existingPhotos.value.forEach((item) => revokeObjectUrl(item.previewUrl))
    existingPhotos.value = []
  }

  const loadExistingPhotos = async (logId) => {
    const { data } = await api.get(`/attachments?order_type=construction_log&order_id=${logId}`)
    const items = data.filter((item) => (item.content_type || '').startsWith('image/'))
    const withPreview = await Promise.all(
      items.map(async (item) => ({
        id: item.id,
        name: item.filename,
        previewUrl: await loadAttachmentPreviewUrl(item.id)
      }))
    )
    existingPhotos.value = withPreview
  }

  const removeExistingPhoto = async (attachmentId) => {
    try {
      await api.delete(`/attachments/${attachmentId}`)
      existingPhotos.value = existingPhotos.value.filter((item) => item.id !== attachmentId)
      notify.success('已删除图片')
    } catch (e) {
      notify.error(e.response?.data?.detail || '删除图片失败')
    }
  }

  const onPhotoChange = (file, fileList) => {
    const prevMap = new Map(photoFileList.value.map((item) => [item.uid, item]))
    const type = file?.raw?.type || file?.raw?.mime || ''
    if (type && !type.startsWith('image/')) {
      notify.error('仅支持图片文件')
      photoFileList.value = fileList.filter((item) => item.uid !== file.uid)
      return
    }

    let nextList = fileList.filter((item) => {
      const itemType = item?.raw?.type || item?.raw?.mime || ''
      return !itemType || itemType.startsWith('image/')
    })

    const remain = Math.max(0, maxPhotos - existingPhotos.value.length)
    if (nextList.length > remain) {
      notify.warning('照片数量已达上限')
      nextList = nextList.slice(0, remain)
    }

    photoFileList.value = nextList.map((item) => {
      if (!item.previewUrl && item.raw) {
        item.previewUrl = URL.createObjectURL(item.raw)
      }
      return item
    })

    const nextUidSet = new Set(photoFileList.value.map((item) => item.uid))
    prevMap.forEach((item, uid) => {
      if (!nextUidSet.has(uid)) {
        revokeObjectUrl(item.previewUrl)
      }
    })
  }

  const removePhoto = (uid) => {
    const target = photoFileList.value.find((item) => item.uid === uid)
    revokeObjectUrl(target?.previewUrl)
    photoFileList.value = photoFileList.value.filter((item) => item.uid !== uid)
  }

  const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms))

  const uploadPhotoWithRetry = async (logId, file, maxAttempts = 2) => {
    let lastError = null
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const formData = new FormData()
        formData.append('file', file)
        await api.post(`/attachments/upload?order_type=construction_log&order_id=${logId}`, formData)
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

  const uploadPhotosForLog = async (logId) => {
    const files = photoFileList.value
      .map((item) => item.raw)
      .filter((item) => item && (item.type || '').startsWith('image/'))

    if (!files.length) return 0
    if (existingPhotos.value.length + files.length > maxPhotos) {
      throw new Error('照片数量已达上限')
    }

    let uploaded = 0
    for (const file of files) {
      await uploadPhotoWithRetry(logId, file, 2)
      uploaded += 1
    }

    return uploaded
  }

  return {
    albumInputRef,
    existingPhotos,
    existingPhotoUrls,
    newPhotoUrls,
    onPhotoExceed,
    appendRawPhotoFiles,
    onNativePhotoPicked,
    openMobilePhotoPicker,
    clearPhotoFiles,
    clearExistingPhotos,
    loadExistingPhotos,
    removeExistingPhoto,
    onPhotoChange,
    removePhoto,
    uploadPhotosForLog,
    photoFileList,
    loadAttachmentPreviewUrl,
    revokeObjectUrl
  }
}
