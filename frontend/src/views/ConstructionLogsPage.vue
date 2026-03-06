<template>
  <div class="page-card module-page logs-manage-page">
    <StockHeadBar title="施工日志" :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage">
      <template #actions>
        <ToolbarSearchInput v-model="keyword" placeholder="按日期/天气/内容搜索" @input="onKeywordInput" />
        <ToolbarIconAction tooltip="新增日志" aria-label="新增日志" type="primary" :disabled="saving || deletingSelected" @click="openCreateDialog">
          <Plus />
        </ToolbarIconAction>
        <ToolbarIconAction tooltip="删除选中" aria-label="删除选中" type="danger" :disabled="!selectedIds.length || saving || deletingSelected" @click="deleteSelected">
          <Delete />
        </ToolbarIconAction>
      </template>
    </StockHeadBar>

    <el-table v-loading="listLoading" class="clickable-table uniform-row-table" :data="rows" border @selection-change="onSelectionChange" @row-click="onRowClick">
      <el-table-column type="selection" width="50" />
      <el-table-column label="序号" width="70" align="center" column-key="skip-row-open">
        <template #default="scope">
          <button type="button" class="log-index-btn" @click.stop="viewRow(scope.row)" aria-label="查看日志详情">
            {{ formatIndex(scope.$index) }}
          </button>
        </template>
      </el-table-column>
      <el-table-column prop="log_date" label="日期" width="130" />
      <el-table-column prop="weather" label="天气" width="120">
        <template #default="scope">
          <span v-if="weatherMetaMap[scope.row.weather]" class="weather-cell">
            <span class="weather-icon">{{ weatherMetaMap[scope.row.weather].icon }}</span>
            <span>{{ weatherMetaMap[scope.row.weather].label }}</span>
          </span>
          <span v-else>{{ scope.row.weather || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="content" label="内容" min-width="320" />
      <el-table-column label="操作" width="60" column-key="skip-row-open">
        <template #default="scope">
          <el-tooltip content="编辑" placement="top">
            <el-button link @click.stop="editRow(scope.row)" aria-label="编辑">
              <el-icon><Edit /></el-icon>
            </el-button>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="open"
      top="8vh"
      width="min(1100px, 94vw)"
      class="log-dialog macos-dialog"
      :fullscreen="isMobileDialog"
      :show-close="false"
      :close-on-press-escape="false"
    >
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="closeFormDialog" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">{{ editingId ? '编辑日志' : '新建日志' }}</div>
          <div class="dialog-header-actions">
            <el-tooltip content="保存" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="保存" :disabled="saving" @click="save">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <el-form label-width="0">
        <div class="log-top-row">
          <el-form-item class="log-top-item">
            <el-input v-model="logDateInput" placeholder="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item class="log-top-item">
            <el-select v-model="form.weather" placeholder="选择天气" filterable clearable style="width: 100%">
              <template #suffix>
                <span v-if="selectedWeatherMeta" class="weather-select-suffix">{{ selectedWeatherMeta.icon }}</span>
              </template>
              <el-option
                v-for="item in weatherOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              >
                <div class="weather-option">
                  <span class="weather-icon">{{ item.icon }}</span>
                  <span>{{ item.label }}</span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>
        </div>
        <el-form-item>
          <el-input
            ref="contentInputRef"
            :key="`log-content-${formFullscreen ? 'full' : 'normal'}-${editingId ? 'edit' : 'create'}`"
            v-model="form.content"
            class="log-content-input"
            type="textarea"
            :autosize="contentAutosize"
            resize="none"
            placeholder="请输入施工日志内容（支持 Markdown）"
          />
        </el-form-item>
        <el-form-item>
          <div class="photo-upload-row">
            <button v-if="isMobileDialog" type="button" class="photo-add-btn" aria-label="上传照片" @click="openMobilePhotoPicker">
              <el-icon><Plus /></el-icon>
            </button>

            <el-upload
              v-else
              v-model:file-list="photoFileList"
              class="photo-upload"
              :multiple="false"
              :auto-upload="false"
              accept="image/*"
              :show-file-list="false"
              :limit="MAX_PHOTOS"
              :on-exceed="onPhotoExceed"
              :on-change="onPhotoChange"
            >
              <div class="photo-add-btn" aria-label="上传照片">
                <el-icon><Plus /></el-icon>
              </div>
            </el-upload>

            <input
              ref="albumInputRef"
              class="native-photo-input"
              type="file"
              accept="image/*"
              @change="onNativePhotoPicked"
            />
            <div class="photo-preview-list" v-if="editingId && existingPhotos.length">
              <div v-for="(item, index) in existingPhotos" :key="item.id" class="photo-preview-item">
                <el-image
                  class="photo-preview-image"
                  :src="item.previewUrl"
                  :alt="item.name || `existing-photo-${index + 1}`"
                  :preview-src-list="existingPhotoUrls"
                  :initial-index="index"
                  fit="cover"
                  preview-teleported
                  hide-on-click-modal
                />
                <button class="remove-btn" type="button" @click="removeExistingPhoto(item.id)" aria-label="删除已上传图片">×</button>
                <span class="order-tag">{{ index + 1 }}</span>
              </div>
            </div>

            <div class="photo-preview-list" v-if="photoFileList.length">
              <div v-for="(item, index) in photoFileList" :key="item.uid" class="photo-preview-item">
                <el-image
                  class="photo-preview-image"
                  :src="item.previewUrl"
                  :alt="item.name || `photo-${index + 1}`"
                  :preview-src-list="newPhotoUrls"
                  :initial-index="index"
                  fit="cover"
                  preview-teleported
                  hide-on-click-modal
                />
                <button class="remove-btn" type="button" @click="removePhoto(item.uid)">×</button>
                <span class="order-tag">{{ existingPhotos.length + index + 1 }}</span>
              </div>
            </div>
          </div>
        </el-form-item>
      </el-form>
    </el-dialog>

    <el-dialog v-model="viewOpen" width="min(900px, 92vw)" class="view-dialog macos-dialog" :fullscreen="isMobileDialog" :show-close="false" align-center>
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="closeViewDialog" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">日志详情</div>
        </div>
      </template>
      <div class="view-grid">
        <div>日期：{{ viewingRow.log_date || '-' }}</div>
        <div>
          天气：
          <span v-if="weatherMetaMap[viewingRow.weather]" class="weather-cell">
            <span class="weather-icon">{{ weatherMetaMap[viewingRow.weather].icon }}</span>
            <span>{{ weatherMetaMap[viewingRow.weather].label }}</span>
          </span>
          <span v-else>{{ viewingRow.weather || '-' }}</span>
        </div>
      </div>
      <div class="view-content markdown-content" v-html="renderedViewingContent"></div>
      <div class="view-photos" v-if="viewingPhotos.length">
        <div class="view-photos-title">现场照片</div>
        <div class="view-photos-grid">
          <div v-for="(photo, index) in viewingPhotos" :key="photo.id" class="view-photo-item">
            <el-image
              class="view-photo-image"
              :src="photo.previewUrl"
              :preview-src-list="viewingPhotoUrls"
              :initial-index="index"
              fit="cover"
              preview-teleported
              hide-on-click-modal
            />
            <button class="view-remove-btn" type="button" aria-label="删除图片" @click="removeViewingPhoto(photo.id)">×</button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Delete, Edit, Plus } from '@element-plus/icons-vue'
import api from '../api'
import ToolbarSearchInput from '../components/ToolbarSearchInput.vue'
import ToolbarIconAction from '../components/ToolbarIconAction.vue'
import StockHeadBar from '../components/StockHeadBar.vue'
import { formatDateInput } from '../utils/date'
import { useRequestLatest } from '../composables/useRequestLatest'
import { usePagedApiList } from '../composables/usePagedApiList'

const keyword = ref('')
const selectedPageSize = 10
const MAX_PHOTOS = 30
const selectedIds = ref([])
const open = ref(false)
const editingId = ref(null)
const saving = ref(false)
const deletingSelected = ref(false)
const formFullscreen = ref(true)
const viewOpen = ref(false)
const contentInputRef = ref(null)
let contentResizeTimer = null
const isMobileDialog = ref(false)
const viewingRow = ref({
  log_date: '',
  weather: '',
  content: ''
})
const contentAutosize = computed(() => (formFullscreen.value ? { minRows: 16, maxRows: 22 } : { minRows: 10, maxRows: 14 }))
const viewingPhotos = ref([])
const viewingPhotoUrls = ref([])
const viewingRequest = useRequestLatest()
const {
  rows,
  page,
  totalPages,
  loading: listLoading,
  load,
  prevPage,
  nextPage,
  resetPage,
  invalidate
} = usePagedApiList({
  pageSize: selectedPageSize,
  errorMessage: '加载施工日志失败',
  fetchPage: ({ page, pageSize }) => api.get('/construction-logs', { params: { keyword: keyword.value, page, page_size: pageSize } }),
  onLoadSuccess: () => {
    selectedIds.value = []
  }
})
const existingPhotos = ref([])
const photoFileList = ref([])
const albumInputRef = ref(null)
const form = reactive({
  log_date: '',
  weather: '',
  content: ''
})

const logDateInput = computed({
  get: () => form.log_date,
  set: (value) => {
    form.log_date = formatDateInput(value)
  }
})

const weatherOptions = [
  { label: '晴', value: '晴', icon: '☀️' },
  { label: '晴间多云', value: '晴间多云', icon: '🌤️' },
  { label: '多云', value: '多云', icon: '⛅' },
  { label: '阴', value: '阴', icon: '☁️' },
  { label: '阵雨', value: '阵雨', icon: '🌦️' },
  { label: '小雨', value: '小雨', icon: '🌧️' },
  { label: '雷雨', value: '雷雨', icon: '⛈️' },
  { label: '雷阵雨', value: '雷阵雨', icon: '🌩️' },
  { label: '雨夹雪', value: '雨夹雪', icon: '🌨️' },
  { label: '小雪', value: '小雪', icon: '❄️' },
  { label: '雾', value: '雾', icon: '🌫️' },
  { label: '大风', value: '大风', icon: '💨' }
]
const weatherMetaMap = weatherOptions.reduce((acc, item) => {
  acc[item.value] = item
  return acc
}, {})
const selectedWeatherMeta = computed(() => weatherMetaMap[form.weather] || null)

const existingPhotoUrls = computed(() => existingPhotos.value.map((item) => item.previewUrl).filter(Boolean))
const newPhotoUrls = computed(() => photoFileList.value.map((item) => item.previewUrl).filter(Boolean))

let markdownRendererPromise = null

const createMarkdownRenderer = async () => {
  if (!markdownRendererPromise) {
    markdownRendererPromise = import('markdown-it').then(({ default: MarkdownIt }) => {
      return new MarkdownIt({
        html: false,
        linkify: true,
        breaks: true
      })
    })
  }
  return markdownRendererPromise
}

const renderedViewingContent = ref('<p>暂无内容</p>')

const updateRenderedViewingContent = async () => {
  const text = (viewingRow.value.content || '').trim()
  if (!text) {
    renderedViewingContent.value = '<p>暂无内容</p>'
    return
  }
  const md = await createMarkdownRenderer()
  renderedViewingContent.value = md.render(text)
}

const updateMobileDialog = () => {
  isMobileDialog.value = window.matchMedia('(max-width: 900px)').matches
}

let keywordInputTimer = null

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
  ElMessage.warning('照片数量已达上限')
}

const appendRawPhotoFiles = (rawFiles) => {
  const files = Array.from(rawFiles || [])
  if (!files.length) return

  const imageFiles = files.filter((file) => (file?.type || '').startsWith('image/'))
  if (imageFiles.length !== files.length) {
    ElMessage.error('仅支持图片文件')
  }
  if (!imageFiles.length) return

  const remain = Math.max(0, MAX_PHOTOS - existingPhotos.value.length)
  const available = Math.max(0, remain - photoFileList.value.length)
  if (!available) {
    ElMessage.warning('照片数量已达上限')
    return
  }

  const accepted = imageFiles.slice(0, available)
  if (accepted.length < imageFiles.length) {
    ElMessage.warning('照片数量已达上限')
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
  photoFileList.value.forEach((item) => {
    if (item?.previewUrl?.startsWith('blob:')) {
      URL.revokeObjectURL(item.previewUrl)
    }
  })
  photoFileList.value = []
}

const clearExistingPhotos = () => {
  existingPhotos.value.forEach((item) => revokeObjectUrl(item.previewUrl))
  existingPhotos.value = []
}

const clearViewingPhotos = () => {
  viewingPhotos.value.forEach((item) => revokeObjectUrl(item.previewUrl))
  viewingPhotos.value = []
  viewingPhotoUrls.value = []
}

const loadExistingPhotos = async (logId) => {
  const { data } = await api.get(`/attachments?order_type=construction_log&order_id=${logId}`)
  const items = data
    .filter((item) => (item.content_type || '').startsWith('image/'))
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
    ElMessage.success('已删除图片')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除图片失败')
  }
}

const onPhotoChange = (file, fileList) => {
  const prevMap = new Map(photoFileList.value.map((item) => [item.uid, item]))
  const type = file?.raw?.type || file?.raw?.mime || ''
  if (type && !type.startsWith('image/')) {
    ElMessage.error('仅支持图片文件')
    photoFileList.value = fileList.filter((item) => item.uid !== file.uid)
    return
  }

  let nextList = fileList.filter((item) => {
    const itemType = item?.raw?.type || item?.raw?.mime || ''
    return !itemType || itemType.startsWith('image/')
  })

  const remain = Math.max(0, MAX_PHOTOS - existingPhotos.value.length)
  if (nextList.length > remain) {
    ElMessage.warning('照片数量已达上限')
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
  if (target?.previewUrl?.startsWith('blob:')) {
    URL.revokeObjectURL(target.previewUrl)
  }
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

  if (existingPhotos.value.length + files.length > MAX_PHOTOS) {
    throw new Error('照片数量已达上限')
  }

  let uploaded = 0
  for (const file of files) {
    await uploadPhotoWithRetry(logId, file, 2)
    uploaded += 1
  }

  return uploaded
}

const onSelectionChange = (items) => {
  selectedIds.value = items.map((i) => i.id)
}

const onRowClick = (row, column) => {
  if (!column || column.type === 'selection' || column.columnKey === 'skip-row-open') return
  viewRow(row)
}

const formatIndex = (index) => String((page.value - 1) * selectedPageSize + index + 1).padStart(2, '0')

const onKeywordInput = () => {
  resetPage()
  if (keywordInputTimer) {
    window.clearTimeout(keywordInputTimer)
  }
  keywordInputTimer = window.setTimeout(() => {
    load()
    keywordInputTimer = null
  }, 250)
}

const viewRow = async (row) => {
  const token = viewingRequest.next()
  viewingRow.value = {
    log_date: row.log_date || '',
    weather: row.weather || '',
    content: row.content || ''
  }
  clearViewingPhotos()
  await updateRenderedViewingContent()
  viewOpen.value = true

  try {
    const { data } = await api.get(`/attachments?order_type=construction_log&order_id=${row.id}`)
    if (!viewingRequest.isLatest(token)) return
    const images = data
      .filter((item) => (item.content_type || '').startsWith('image/'))
    const photos = await Promise.all(
      images.map(async (item) => ({
        id: item.id,
        previewUrl: await loadAttachmentPreviewUrl(item.id)
      }))
    )
    if (!viewingRequest.isLatest(token)) {
      photos.forEach((item) => revokeObjectUrl(item.previewUrl))
      return
    }
    viewingPhotos.value = photos
    viewingPhotoUrls.value = photos.map((item) => item.previewUrl)
  } catch (e) {
    if (!viewingRequest.isLatest(token)) return
    clearViewingPhotos()
    ElMessage.error(e.response?.data?.detail || '加载日志照片失败')
  }
}

const formatDate = (d) => {
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

const openCreateDialog = () => {
  editingId.value = null
  clearPhotoFiles()
  clearExistingPhotos()
  form.log_date = formatDate(new Date())
  form.weather = ''
  form.content = ''
  open.value = true
}

const save = async () => {
  if (saving.value) return
  saving.value = true
  try {
    let logId = editingId.value
    if (editingId.value) {
      await api.put(`/construction-logs/${editingId.value}`, {
        title: form.log_date ? `施工日志-${form.log_date}` : '施工日志',
        log_date: form.log_date,
        weather: form.weather,
        content: form.content
      })
    } else {
      const { data } = await api.post('/construction-logs', {
        ...form,
        title: form.log_date ? `施工日志-${form.log_date}` : '施工日志'
      })
      logId = data.id
    }

    const uploadedCount = await uploadPhotosForLog(logId)

    ElMessage.success(uploadedCount ? `保存成功，已上传 ${uploadedCount} 张照片` : '保存成功')
    open.value = false
    editingId.value = null
    clearPhotoFiles()
    form.log_date = ''
    form.weather = ''
    form.content = ''
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const editRow = async (row) => {
  editingId.value = row.id
  clearPhotoFiles()
  clearExistingPhotos()
  form.log_date = row.log_date || ''
  form.weather = row.weather || ''
  form.content = row.content || ''
  open.value = true
  try {
    await loadExistingPhotos(row.id)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载历史照片失败')
  }
}

const deleteSelected = async () => {
  if (!selectedIds.value.length || deletingSelected.value) return
  deletingSelected.value = true
  try {
    for (const id of selectedIds.value) {
      await api.delete(`/construction-logs/${id}`)
    }
    ElMessage.success('删除成功')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  } finally {
    deletingSelected.value = false
  }
}

const resetLogsPage = async () => {
  resetPage()
  open.value = false
  editingId.value = null
  viewOpen.value = false
  clearViewingPhotos()
  clearPhotoFiles()
  clearExistingPhotos()
  form.log_date = ''
  form.weather = ''
  form.content = ''
  await load()
}

const onResetEvent = () => {
  resetLogsPage()
}

const onCloseAllDialogs = () => {
  open.value = false
  viewOpen.value = false
}

const syncContentTextareaLayout = async () => {
  await nextTick()
  contentInputRef.value?.resizeTextarea?.()
  if (contentResizeTimer) {
    window.clearTimeout(contentResizeTimer)
  }
  contentResizeTimer = window.setTimeout(() => {
    contentInputRef.value?.resizeTextarea?.()
    contentResizeTimer = null
  }, 260)
}

const closeFormDialog = () => {
  open.value = false
}

const closeViewDialog = () => {
  viewingRequest.invalidate()
  viewOpen.value = false
  renderedViewingContent.value = '<p>暂无内容</p>'
}

watch(formFullscreen, () => {
  syncContentTextareaLayout()
})

watch(open, (isOpen) => {
  if (isOpen) {
    syncContentTextareaLayout()
  }
})

const removeViewingPhoto = async (attachmentId) => {
  try {
    await api.delete(`/attachments/${attachmentId}`)
    const target = viewingPhotos.value.find((item) => item.id === attachmentId)
    revokeObjectUrl(target?.previewUrl)
    viewingPhotos.value = viewingPhotos.value.filter((item) => item.id !== attachmentId)
    viewingPhotoUrls.value = viewingPhotos.value.map((item) => item.previewUrl)
    ElMessage.success('已删除图片')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除图片失败')
  }
}

onMounted(() => {
  updateMobileDialog()
  load()
  window.addEventListener('resize', updateMobileDialog)
  window.addEventListener('reset-current-page', onResetEvent)
  window.addEventListener('close-all-dialogs', onCloseAllDialogs)
})

onBeforeUnmount(() => {
  invalidate()
  viewingRequest.invalidate()
  if (keywordInputTimer) {
    window.clearTimeout(keywordInputTimer)
    keywordInputTimer = null
  }
  if (contentResizeTimer) {
    window.clearTimeout(contentResizeTimer)
    contentResizeTimer = null
  }
  clearViewingPhotos()
  clearExistingPhotos()
  clearPhotoFiles()
  window.removeEventListener('resize', updateMobileDialog)
  window.removeEventListener('close-all-dialogs', onCloseAllDialogs)
  window.removeEventListener('reset-current-page', onResetEvent)
})
</script>

<style scoped>
.module-page {
  --log-content-text: color-mix(in oklab, var(--text) 92%, #ffffff 8%);
  --log-content-muted: color-mix(in oklab, var(--muted) 88%, #ffffff 12%);
  --log-content-bg: color-mix(in oklab, var(--panel-solid) 90%, #ffffff 10%);
  --log-content-soft-bg: color-mix(in oklab, var(--panel-solid) 84%, transparent);
  --log-content-border: color-mix(in oklab, var(--divider-strong) 78%, transparent);
}

:global(:root[data-theme='dark']) .module-page {
  --log-content-text: color-mix(in oklab, var(--text) 82%, #ffffff 18%);
  --log-content-muted: color-mix(in oklab, var(--muted) 76%, #ffffff 24%);
  --log-content-bg: color-mix(in oklab, var(--surface-1) 76%, #ffffff 24%);
  --log-content-soft-bg: color-mix(in oklab, var(--surface-1) 72%, #ffffff 28%);
  --log-content-border: color-mix(in oklab, var(--divider-strong) 70%, #ffffff 30%);
}

.log-top-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.log-top-item {
  margin-bottom: 12px;
}

.weather-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.weather-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.weather-icon {
  width: 20px;
  display: inline-flex;
  justify-content: center;
}

.weather-select-prefix {
  display: inline-flex;
  align-items: center;
}

.dialog-header-actions {
  position: absolute;
  left: 0;
  right: auto;
  top: 50%;
  transform: translateY(-50%);
}

.log-index-btn {
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
  font-family: inherit;
  font-weight: inherit;
  font-size: inherit;
  line-height: inherit;
  color: inherit !important;
}

.log-index-btn:hover,
.log-index-btn:focus,
.log-index-btn:active {
  border: none;
  outline: none;
  filter: none;
  text-decoration: none;
}

.photo-upload {
  flex: 0 0 auto;
}

.native-photo-input {
  display: none;
}

.photo-upload-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 2px;
}

.photo-add-btn {
  width: 82px;
  height: 82px;
  border: 1px dashed var(--border);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  background: var(--panel-solid);
  font-size: 24px;
}

.photo-add-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.photo-preview-list {
  display: flex;
  align-items: center;
  gap: 8px;
}

.photo-preview-item {
  width: 82px;
  height: 82px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  background: var(--panel-solid);
}

.photo-preview-image {
  width: 100%;
  height: 100%;
  display: block;
}

.photo-preview-image :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.remove-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: color-mix(in oklab, var(--text) 55%, transparent);
  color: var(--panel-solid);
  cursor: pointer;
  line-height: 18px;
  text-align: center;
  padding: 0;
}

.order-tag {
  position: absolute;
  left: 4px;
  bottom: 4px;
  font-size: 11px;
  padding: 1px 4px;
  border-radius: 10px;
  color: var(--panel-solid);
  background: color-mix(in oklab, var(--text) 60%, transparent);
}

.view-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 10px;
  color: var(--log-content-text);
}

.view-photos {
  margin-top: 12px;
}

.view-photos-title {
  font-size: 13px;
  color: var(--log-content-muted);
  margin-bottom: 8px;
}

.view-photos-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}

.view-photo-item {
  position: relative;
  width: 100%;
  height: 120px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border);
}

.view-photo-image {
  width: 100%;
  height: 100%;
  display: block;
}

.view-photo-image :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.view-remove-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: color-mix(in oklab, var(--text) 55%, transparent);
  color: var(--panel-solid);
  cursor: pointer;
  line-height: 18px;
  text-align: center;
  padding: 0;
}

.view-content {
  line-height: 1.6;
  padding: 10px;
  border: 1px solid var(--log-content-border);
  border-radius: 8px;
  color: var(--log-content-text);
  background: var(--log-content-bg);
}

.log-dialog :deep(.el-textarea__inner),
.log-dialog :deep(.el-input__wrapper),
.log-dialog :deep(.el-select__wrapper) {
  color: var(--log-content-text) !important;
  background: var(--log-content-bg) !important;
  border-color: var(--log-content-border) !important;
}

.log-dialog :deep(.log-content-input .el-textarea__inner) {
  resize: none !important;
  transition: none !important;
  background-clip: padding-box;
  border: 1px solid var(--log-content-border) !important;
  border-radius: 12px !important;
  box-shadow: none !important;
  transform: translateZ(0);
  backface-visibility: hidden;
}

.log-dialog :deep(.el-textarea__inner::placeholder),
.log-dialog :deep(.el-input__inner::placeholder) {
  color: var(--log-content-muted) !important;
}

.markdown-content :deep(p) {
  margin: 0 0 0.8em;
}

.markdown-content :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4) {
  margin: 0.6em 0;
  line-height: 1.35;
}

.markdown-content :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.92em;
  padding: 0.1em 0.3em;
  border-radius: 4px;
  color: var(--log-content-text);
  background: var(--log-content-soft-bg);
}

.markdown-content :deep(pre) {
  margin: 0.8em 0;
  padding: 10px;
  border-radius: 8px;
  overflow: auto;
  border: 1px solid var(--log-content-border);
  background: var(--log-content-soft-bg);
}

.markdown-content :deep(pre code) {
  padding: 0;
  background: transparent;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 0.6em 0;
  padding-left: 1.3em;
}

.markdown-content :deep(a) {
  color: var(--accent);
  text-decoration: none;
}

.markdown-content :deep(a:hover) {
  text-decoration: underline;
}

@media (max-width: 900px) {
  .log-dialog :deep(.el-dialog),
  .view-dialog :deep(.el-dialog) {
    width: min(96vw, 980px) !important;
    margin: 0 auto !important;
    max-height: calc(100dvh - 24px);
    display: flex;
    flex-direction: column;
  }

  .log-dialog :deep(.el-dialog__body),
  .view-dialog :deep(.el-dialog__body) {
    flex: 1;
    max-height: none !important;
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .log-dialog :deep(.el-dialog.is-fullscreen),
  .view-dialog :deep(.el-dialog.is-fullscreen) {
    width: 100vw !important;
    height: 100dvh !important;
    max-height: none;
    margin: 0 !important;
  }

  .log-dialog :deep(.el-dialog.is-fullscreen .el-dialog__body),
  .view-dialog :deep(.el-dialog.is-fullscreen .el-dialog__body) {
    padding-bottom: 12px;
  }

  .log-top-row {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .log-top-item {
    margin-bottom: 10px;
  }

  .photo-add-btn,
  .photo-preview-item {
    width: 68px;
    height: 68px;
  }

  .view-grid {
    grid-template-columns: 1fr;
    gap: 6px;
  }
}
</style>
