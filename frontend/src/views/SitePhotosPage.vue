<template>
  <div ref="pageCardRef" class="page-card module-page photos-manage-page">
    <StockHeadBar :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage">
      <template #actions>
        <el-tooltip content="按日期筛选" placement="bottom">
          <ToolbarSearchInput v-model="selectedDateInput" placeholder="YYYY-MM-DD" class="date-filter-picker" />
        </el-tooltip>
      </template>
      <template #title>
        <div class="stock-dark-segment photos-type-toggle" role="group" aria-label="照片类型筛选">
          <button
            type="button"
            :class="['photos-type-option', { 'is-active': photoTypeFilter === 'log' }]"
            @click="togglePhotoType('log')"
          >
            日志
          </button>
          <button
            type="button"
            :class="['photos-type-option', { 'is-active': photoTypeFilter === 'machine' }]"
            @click="togglePhotoType('machine')"
          >
            机械
          </button>
        </div>
      </template>
    </StockHeadBar>

    <div v-loading="listLoading" class="photos-content">
      <el-empty v-if="!visibleRows.length && !listLoading" description="暂无现场照片" />

      <div :class="['photo-grid', { 'is-animating': gridAnimating }]" :style="photoGridStyle">
        <div v-for="(photo, index) in visibleRows" :key="photo.id" class="photo-card" :title="`大小：${formatSize(photo.size)}`">
          <div class="photo-date-tag">{{ photo.log_date || '未填写日期' }}</div>
          <el-image
            v-if="photo.previewUrl"
            :class="['photo-thumb', { 'is-landscape': photo.isLandscape }]"
            :src="photo.previewUrl"
            :preview-src-list="previewUrls"
            :initial-index="index"
            :fit="photo.isLandscape ? 'cover' : 'contain'"
            preview-teleported
            hide-on-click-modal
          />
          <div v-else class="photo-thumb photo-thumb-placeholder" aria-hidden="true">
            <div class="photo-skeleton photo-skeleton-shimmer"></div>
            <div class="photo-skeleton photo-skeleton-line photo-skeleton-line-wide"></div>
            <div class="photo-skeleton photo-skeleton-line photo-skeleton-line-short"></div>
          </div>
          <button class="photo-remove-btn" type="button" aria-label="删除照片" @click="remove(photo)">×</button>
          <button class="photo-action-btn photo-download-btn" type="button" aria-label="下载照片" @click="forceDownloadAttachment(photo.id)">↓</button>
          <div class="photo-meta-overlay"></div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import api from '../api'
import ToolbarSearchInput from '../components/ToolbarSearchInput.vue'
import StockHeadBar from '../components/StockHeadBar.vue'
import { formatDateInput } from '../utils/date'
import { useRequestLatest } from '../composables/useRequestLatest'
import { useLoadGuard } from '../composables/useLoadGuard'
import { notify } from '../utils/notify'
import { readPreference, storageKeys } from '../utils/storage'

const allRows = ref([])
const visibleRows = ref([])
const page = ref(1)
const photoCols = ref(5)
const isMobileLayout = ref(window.matchMedia('(max-width: 900px)').matches)
const pageCardRef = ref(null)
const isSidebarCollapsed = ref(readPreference(storageKeys.preferences.sidebarCollapsed) === '1')
const pcExpandedThreeRowHeight = ref(0)
const gridAnimating = ref(false)
const { loading: listLoading, run: runLoad } = useLoadGuard()
const PHOTO_LAYOUT = {
  mobileColsByWidth: [
    { max: 760, cols: 2 },
    { max: 1040, cols: 3 },
    { max: 1320, cols: 4 },
    { max: 1600, cols: 5 }
  ],
  desktopCols: { expanded: 5, collapsed: 6 },
  pageRows: { mobile: 5, desktop: 3 },
  baseRowGap: 14,
  rowGapMax: 72,
  colGapDefaults: { twoCols: '10px', threeColsWide: '14px', threeColsNarrow: '8px', threeColsCollapsed: '12px', threeColsExpanded: '9px', fivePlus: '12px', fallback: '11px' }
}
const pageSize = computed(() => {
  const rowsPerPage = isMobileLayout.value ? PHOTO_LAYOUT.pageRows.mobile : PHOTO_LAYOUT.pageRows.desktop
  return Math.max(1, photoCols.value * rowsPerPage)
})
const today = () => {
  const d = new Date()
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}
const selectedDate = ref(today())
const dateFilterActivated = ref(false)
const photoTypeFilter = ref('')

const togglePhotoType = (type) => {
  photoTypeFilter.value = photoTypeFilter.value === type ? '' : type
  page.value = 1
}

const selectedDateInput = computed({
  get: () => selectedDate.value,
  set: (value) => {
    selectedDate.value = formatDateInput(value)
  }
})

const detectLandscape = (url) =>
  new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve((img.naturalWidth || 0) >= (img.naturalHeight || 0))
    img.onerror = () => resolve(false)
    img.src = url
  })

const loadAttachmentPreviewUrl = async (attachmentId) => {
  const { data } = await api.get(`/attachments/${attachmentId}/download`, { responseType: 'blob' })
  const previewUrl = URL.createObjectURL(data)
  const isLandscape = await detectLandscape(previewUrl)
  return { previewUrl, isLandscape }
}

const parseFilenameFromDisposition = (disposition) => {
  const text = String(disposition || '')
  if (!text) return ''
  const utf8Match = text.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]).replace(/\+/g, ' ')
    } catch {
      return utf8Match[1]
    }
  }
  const plainMatch = text.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1] || ''
}

const inferExtByType = (contentType) => {
  const ct = String(contentType || '').toLowerCase()
  if (ct.includes('image/webp')) return '.webp'
  if (ct.includes('image/jpeg')) return '.jpg'
  if (ct.includes('image/png')) return '.png'
  if (ct.includes('application/pdf')) return '.pdf'
  return ''
}

const hasExt = (name) => /\.[A-Za-z0-9]+$/.test(name)

const sanitizeName = (name, fallbackExt = '') => {
  const normalized = String(name || '').replace(/[\\/:*?"<>|]/g, '_').trim()
  if (!normalized) return `attachment${fallbackExt}`
  if (hasExt(normalized)) return normalized
  return `${normalized}${fallbackExt}`
}

const forceDownloadAttachment = async (attachmentId) => {
  try {
    const response = await api.get(`/attachments/${attachmentId}/download`, { responseType: 'blob' })
    const blob = response.data
    const ext = inferExtByType(response.headers?.['content-type'])
    const fromHeader = parseFilenameFromDisposition(response.headers?.['content-disposition'])
    const filename = sanitizeName(fromHeader, ext)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    notify.error(e.response?.data?.detail || '下载失败')
  }
}

const revokeObjectUrl = (url) => {
  if (url?.startsWith('blob:')) {
    URL.revokeObjectURL(url)
  }
}

const clearPreviewUrls = (rows = visibleRows.value) => {
  rows.forEach((item) => revokeObjectUrl(item.previewUrl))
}

const filteredRows = computed(() => {
  let list = allRows.value
  if (photoTypeFilter.value) {
    list = list.filter((item) => item.source_type === photoTypeFilter.value)
  }
  if (!dateFilterActivated.value || !selectedDate.value) return list
  return list.filter((item) => item.log_date === selectedDate.value)
})

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredRows.value.slice(start, start + pageSize.value)
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize.value)))

const calcPhotoCols = (width) => {
  const matched = PHOTO_LAYOUT.mobileColsByWidth.find((rule) => width <= rule.max)
  return matched ? matched.cols : PHOTO_LAYOUT.desktopCols.collapsed
}

const updatePhotoCols = () => {
  isMobileLayout.value = window.matchMedia('(max-width: 900px)').matches
  if (!isMobileLayout.value) {
    photoCols.value = isSidebarCollapsed.value ? PHOTO_LAYOUT.desktopCols.collapsed : PHOTO_LAYOUT.desktopCols.expanded
    if (!isSidebarCollapsed.value) {
      const hostWidth = pageCardRef.value?.clientWidth || window.innerWidth
      const colGap = Number.parseFloat(photoGridGap.value) || 12
      const cellWidth = (hostWidth - (PHOTO_LAYOUT.desktopCols.expanded - 1) * colGap) / PHOTO_LAYOUT.desktopCols.expanded
      const cellHeight = Math.max(0, cellWidth * 0.75)
      pcExpandedThreeRowHeight.value = PHOTO_LAYOUT.pageRows.desktop * cellHeight + (PHOTO_LAYOUT.pageRows.desktop - 1) * PHOTO_LAYOUT.baseRowGap
    }
    return
  }
  const hostWidth = pageCardRef.value?.clientWidth || window.innerWidth
  photoCols.value = calcPhotoCols(hostWidth)
}

const onSidebarCollapseChanged = (event) => {
  isSidebarCollapsed.value = Boolean(event?.detail?.collapsed)
  updatePhotoCols()
  triggerGridAnimation()
}

const photoGridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${photoCols.value}, minmax(0, 1fr))`,
  columnGap: photoGridGap.value,
  rowGap: photoGridRowGap.value
}))

const photoGridRowGap = computed(() => {
  if (isMobileLayout.value) return '0'
  const baseGap = PHOTO_LAYOUT.baseRowGap
  if (photoCols.value === PHOTO_LAYOUT.desktopCols.expanded) return `${baseGap}px`

  const hostWidth = pageCardRef.value?.clientWidth || window.innerWidth
  if (!hostWidth) return `${baseGap}px`

  const colGap = Number.parseFloat(photoGridGap.value) || 12
  const currentCellWidth = (hostWidth - (PHOTO_LAYOUT.desktopCols.collapsed - 1) * colGap) / PHOTO_LAYOUT.desktopCols.collapsed
  const currentCellHeight = Math.max(0, currentCellWidth * 0.75)
  const rowsCount = PHOTO_LAYOUT.pageRows.desktop
  const targetThreeRowHeight = pcExpandedThreeRowHeight.value > 0 ? pcExpandedThreeRowHeight.value : (rowsCount * currentCellHeight + (rowsCount - 1) * baseGap)
  const solvedGap = (targetThreeRowHeight - rowsCount * currentCellHeight) / Math.max(1, rowsCount - 1)
  const safeGap = Math.max(baseGap, Math.min(PHOTO_LAYOUT.rowGapMax, Number.isFinite(solvedGap) ? solvedGap : baseGap))
  return `${safeGap}px`
})

const photoGridGap = computed(() => {
  const hostWidth = pageCardRef.value?.clientWidth || window.innerWidth
  if (photoCols.value === 3) {
    if (hostWidth >= 980) return PHOTO_LAYOUT.colGapDefaults.threeColsWide
    if (hostWidth <= 860) return PHOTO_LAYOUT.colGapDefaults.threeColsNarrow
    return isSidebarCollapsed.value ? PHOTO_LAYOUT.colGapDefaults.threeColsCollapsed : PHOTO_LAYOUT.colGapDefaults.threeColsExpanded
  }
  if (photoCols.value === 2) return PHOTO_LAYOUT.colGapDefaults.twoCols
  if (photoCols.value >= 5) return PHOTO_LAYOUT.colGapDefaults.fivePlus
  return PHOTO_LAYOUT.colGapDefaults.fallback
})

let pageResizeObserver = null
let gridAnimationTimer = null
const loadRequest = useRequestLatest()
const previewRequest = useRequestLatest()

const triggerGridAnimation = () => {
  if (gridAnimationTimer) {
    clearTimeout(gridAnimationTimer)
    gridAnimationTimer = null
  }
  gridAnimating.value = false
  requestAnimationFrame(() => {
    gridAnimating.value = true
    gridAnimationTimer = setTimeout(() => {
      gridAnimating.value = false
      gridAnimationTimer = null
    }, 360)
  })
}

const previewUrls = computed(() => visibleRows.value.map((item) => item.previewUrl).filter(Boolean))

const formatSize = (size) => {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

const loadVisiblePreviews = async () => {
  const token = previewRequest.next()
  const previousRows = visibleRows.value
  const baseRows = pagedRows.value.map((item) => ({
    ...item,
    previewUrl: '',
    isLandscape: false
  }))

  clearPreviewUrls(previousRows)
  visibleRows.value = baseRows
  if (!baseRows.length) {
    return
  }

  try {
    const hydratedRows = await Promise.all(
      baseRows.map(async (item) => ({
        ...item,
        ...(await loadAttachmentPreviewUrl(item.id))
      }))
    )
    if (!previewRequest.isLatest(token)) {
      clearPreviewUrls(hydratedRows)
      return
    }
    visibleRows.value = hydratedRows
  } catch (e) {
    if (!previewRequest.isLatest(token)) return
    clearPreviewUrls()
    visibleRows.value = baseRows
    notify.error(e.response?.data?.detail || '加载照片预览失败')
  }
}

const load = async () => {
  const token = loadRequest.next()
  await runLoad(
    async () => {
      const { data } = await api.get('/site-photos')
      if (!loadRequest.isLatest(token)) return
      allRows.value = data
        .map((item) => ({
          ...item
        }))
        .sort((a, b) => {
        const dateCompare = String(b.log_date || '').localeCompare(String(a.log_date || ''))
        if (dateCompare !== 0) return dateCompare
        return Number(b.id || 0) - Number(a.id || 0)
      })
      if (page.value > totalPages.value) {
        page.value = totalPages.value
      }
      await loadVisiblePreviews()
    },
    (e) => {
      if (!loadRequest.isLatest(token)) return
      notify.error(e.response?.data?.detail || '加载现场照片失败')
    }
  )
}

const prevPage = () => {
  if (page.value <= 1) return
  page.value -= 1
}

const nextPage = () => {
  if (page.value >= totalPages.value) return
  page.value += 1
}

const remove = async (photo) => {
  try {
    await ElMessageBox.confirm('删除后不可恢复，确定删除该照片吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    await api.delete(`/attachments/${photo.id}`)
    notify.success('删除成功')
    await load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      notify.error(e.response?.data?.detail || '删除失败')
    }
  }
}

const onResetEvent = () => {
  page.value = 1
  load()
}

watch(pageSize, () => {
  if (page.value > totalPages.value) {
    page.value = totalPages.value
  }
})

watch(pagedRows, () => {
  loadVisiblePreviews()
})

watch(selectedDate, () => {
  dateFilterActivated.value = true
  page.value = 1
})

onMounted(() => {
  updatePhotoCols()
  window.addEventListener('reset-current-page', onResetEvent)
  window.addEventListener('resize', updatePhotoCols)
  window.addEventListener('sidebar-collapse-changed', onSidebarCollapseChanged)
  if (typeof ResizeObserver !== 'undefined' && pageCardRef.value) {
    pageResizeObserver = new ResizeObserver(updatePhotoCols)
    pageResizeObserver.observe(pageCardRef.value)
  }
  load()
})

onBeforeUnmount(() => {
  loadRequest.invalidate()
  previewRequest.invalidate()
  clearPreviewUrls()
  window.removeEventListener('reset-current-page', onResetEvent)
  window.removeEventListener('resize', updatePhotoCols)
  window.removeEventListener('sidebar-collapse-changed', onSidebarCollapseChanged)
  if (pageResizeObserver) {
    pageResizeObserver.disconnect()
    pageResizeObserver = null
  }
  if (gridAnimationTimer) {
    clearTimeout(gridAnimationTimer)
    gridAnimationTimer = null
  }
})
</script>

<style scoped>
.photos-manage-page {
  min-height: calc(100dvh - 40px);
  display: flex;
  flex-direction: column;
}

.photos-content {
  flex: 1;
  padding-bottom: 0;
}

.photos-manage-page :deep(.stock-page-head .stock-page-title) {
  width: auto;
  max-width: none;
  min-height: auto;
  height: auto;
  padding: 0;
  border: none;
  background: transparent;
  box-shadow: none;
}

.photos-type-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0;
  padding: 2px;
  min-width: 0;
}

.photos-type-option {
  appearance: none;
  -webkit-appearance: none;
  border: none;
  border-radius: 999px;
  min-width: 84px;
  height: 30px;
  padding: 0 14px;
  background: transparent !important;
  color: var(--segment-text) !important;
  font-size: 14px;
  font-weight: 600;
  line-height: 30px;
  cursor: pointer;
}

.photos-type-option:hover {
  color: var(--segment-text-hover);
}

.photos-type-option.is-active {
  background: var(--segment-active-bg) !important;
  color: var(--segment-active-text) !important;
}

.photos-type-option.is-active:hover,
.photos-type-option.is-active:focus,
.photos-type-option.is-active:active {
  color: var(--segment-active-text) !important;
}

.photo-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  width: 100%;
  max-width: 100%;
}

.photo-card {
  position: relative;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  background: color-mix(in oklab, var(--surface-2) 92%, var(--bg) 8%);
  min-width: 0;
}

.photo-grid.is-animating .photo-card {
  animation: none;
}

@keyframes photo-skeleton-sweep {
  100% {
    transform: translateX(100%);
  }
}

.photo-thumb {
  width: 100%;
  aspect-ratio: 4 / 3;
  display: block;
  background: color-mix(in oklab, var(--surface-2) 88%, var(--bg) 12%);
}

.photo-thumb-placeholder {
  position: relative;
  padding: 14px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 8px;
  border: 1px solid color-mix(in oklab, var(--divider-strong) 62%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in oklab, #ffffff 28%, transparent);
}

.photo-thumb-placeholder::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, color-mix(in oklab, var(--surface-1) 26%, transparent), transparent 55%);
  pointer-events: none;
}

.photo-thumb-placeholder::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 22% 18%, color-mix(in oklab, #ffffff 12%, transparent), transparent 42%);
  pointer-events: none;
}

.photo-skeleton {
  position: relative;
  z-index: 1;
  border-radius: 10px;
  background: color-mix(in oklab, var(--surface-1) 58%, var(--surface-3) 42%);
  overflow: hidden;
  border: 1px solid color-mix(in oklab, var(--divider-strong) 36%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in oklab, #ffffff 18%, transparent);
}

.photo-skeleton-shimmer {
  flex: 1;
  min-height: 0;
  min-height: 52%;
}

.photo-skeleton-line {
  height: 10px;
}

.photo-skeleton-line-wide {
  width: 68%;
}

.photo-skeleton-line-short {
  width: 42%;
}

.photo-skeleton::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.2) 48%, transparent 100%);
  transform: translateX(-100%);
  animation: photo-skeleton-sweep 1.4s ease-in-out infinite;
}

:root[data-theme='dark'] .photo-thumb-placeholder {
  border-color: color-mix(in oklab, var(--divider-strong) 84%, transparent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), inset 0 -12px 24px rgba(4, 8, 16, 0.18);
}

:root[data-theme='dark'] .photo-thumb-placeholder::before {
  background: radial-gradient(circle at 22% 18%, rgba(255, 255, 255, 0.05), transparent 42%);
}

:root[data-theme='dark'] .photo-skeleton {
  border-color: color-mix(in oklab, var(--divider-strong) 72%, transparent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), inset 0 -8px 16px rgba(3, 7, 14, 0.14);
}

:root[data-theme='dark'] .photo-skeleton::before {
  background: linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.08) 48%, transparent 100%);
}

.photo-thumb :deep(.el-image__wrapper),
.photo-thumb :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  display: block;
}

.photo-thumb :deep(.el-image__wrapper),
.photo-thumb :deep(.el-image__placeholder),
.photo-thumb :deep(.el-image__error) {
  background: color-mix(in oklab, var(--surface-2) 88%, var(--bg) 12%) !important;
}

.photos-content :deep(.el-loading-mask) {
  background: color-mix(in oklab, var(--surface-2) 82%, transparent) !important;
  backdrop-filter: blur(3px);
}

.photo-thumb :deep(.el-image__inner) {
  object-fit: contain;
}

.photo-thumb.is-landscape :deep(.el-image__inner) {
  object-fit: cover;
}

.photo-meta-overlay {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 8px 10px;
  background: linear-gradient(180deg, transparent 0%, color-mix(in oklab, var(--text) 66%, transparent) 100%);
  pointer-events: none;
}

.photo-remove-btn,
.photo-download-btn {
  position: absolute;
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
  z-index: 2;
}

.photo-remove-btn {
  top: 6px;
  right: 6px;
}

.photo-download-btn {
  right: 6px;
  bottom: 6px;
}

.photo-date-tag {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 2;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1.2;
  color: var(--panel-solid);
  background: color-mix(in oklab, var(--text) 58%, transparent);
  backdrop-filter: blur(4px);
  pointer-events: none;
}

.date-filter-picker {
  width: 152px;
}

@media (max-width: 900px) {
  .photos-manage-page :deep(.stock-page-head .stock-page-title) {
    grid-area: title;
    margin: 0;
    align-self: center;
    justify-self: center;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 30px;
    height: 30px;
    min-width: 150px;
    padding: 3px 10px;
    font-size: 13px;
    line-height: 1;
    border: 1px solid var(--segment-shell-border);
    background: var(--segment-shell-bg);
    color: var(--segment-active-text);
    box-shadow: var(--segment-shell-shadow);
    border-radius: 999px;
  }

  .photos-type-toggle {
    width: auto;
    max-width: none;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    padding: 0;
    border: none;
    background: transparent;
    box-shadow: none;
    border-radius: 0;
  }

  .photos-type-option {
    flex: 0 0 auto;
    width: 72px;
    min-width: 72px;
    max-width: 72px;
    height: 26px;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 600;
    line-height: 26px;
  }

  .photos-manage-page {
    min-height: 0;
    padding-bottom: 0;
  }

  .photo-grid.is-animating .photo-card {
    animation: none;
  }

  .photo-grid {
    column-gap: 10px;
    row-gap: 0;
  }

}
</style>
