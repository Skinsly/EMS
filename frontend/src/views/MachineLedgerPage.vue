<template>
  <div class="page-card module-page machine-manage-page">
    <StockHeadBar title="机械台账" :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage">
      <template #actions>
        <ToolbarSearchInput v-model="keyword" placeholder="按名称/规格搜索" @enter="load" />
        <ToolbarIconAction tooltip="新增机械" aria-label="新增机械" type="primary" :disabled="saving || deleting" @click="openCreateDialog">
          <Plus />
        </ToolbarIconAction>
        <ToolbarIconAction tooltip="删除选中" aria-label="删除选中" type="danger" :disabled="!selectedIds.length || saving || deleting" @click="deleteSelected">
          <Delete />
        </ToolbarIconAction>
        <ToolbarIconAction tooltip="导出台班" aria-label="导出台班" @click="download">
          <Download />
        </ToolbarIconAction>
      </template>
    </StockHeadBar>

    <el-table v-loading="listLoading" class="uniform-row-table clickable-table" :data="rows" border @selection-change="onSelectionChange" @row-click="openDetailByRow">
      <el-table-column type="selection" width="50" />
      <el-table-column label="序号" width="70">
        <template #default="scope">{{ formatIndex(scope.$index) }}</template>
      </el-table-column>
      <el-table-column prop="use_date" label="施工日期" width="140" />
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="spec" label="规格" min-width="160" />
      <el-table-column prop="shift_count" label="台班" width="110" />
      <el-table-column prop="remark" label="备注" min-width="200" />
      <el-table-column label="操作" width="60">
        <template #default="scope">
          <el-tooltip content="编辑" placement="top">
            <el-button link type="primary" @click.stop="editRow(scope.row)" aria-label="编辑">
              <el-icon><Edit /></el-icon>
            </el-button>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="open" width="min(620px, 92vw)" class="macos-dialog machine-ledger-dialog" :show-close="false" :close-on-press-escape="false">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="closeCreateDialog" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">{{ editingId ? '编辑台班' : '新建台班' }}</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="确认" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="确认" :disabled="saving" @click="save">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>

      <el-form label-width="0" @keydown.enter.prevent="save">
        <div class="machine-form-row">
          <el-form-item class="machine-form-col"><el-input v-model="form.name" placeholder="机械名称" /></el-form-item>
          <el-form-item class="machine-form-col"><el-input v-model="form.spec" placeholder="机械规格" /></el-form-item>
        </div>
        <div class="machine-form-row">
          <el-form-item class="machine-form-col"><el-input v-model="useDateInput" placeholder="使用日期 YYYY-MM-DD" /></el-form-item>
          <el-form-item class="machine-form-col machine-shift-input">
            <el-input v-model="shiftCountInput" placeholder="台班" />
          </el-form-item>
        </div>
        <el-form-item class="machine-remark-item"><el-input v-model="form.remark" placeholder="备注" /></el-form-item>

        <div class="photo-upload-row">
          <button class="photo-add-btn" type="button" aria-label="上传照片" @click="openPhotoPicker"><span class="photo-add-plus">+</span></button>
          <div class="photo-preview-list" v-if="photoFileList.length">
            <div v-for="(item, index) in photoFileList" :key="item.uid" class="photo-preview-item">
              <el-image
                class="photo-preview-image"
                :src="item.previewUrl"
                :preview-src-list="photoPreviewUrls"
                :initial-index="index"
                fit="cover"
                preview-teleported
                hide-on-click-modal
              />
              <button class="remove-preview-btn" type="button" aria-label="移除照片" @click="removePhoto(item.uid)">×</button>
            </div>
          </div>
          <input ref="albumInputRef" class="native-photo-input" type="file" accept="image/*" multiple @change="onNativePhotoChange" />
        </div>
      </el-form>
    </el-dialog>

    <el-dialog v-model="detailOpen" width="min(620px, 92vw)" class="macos-dialog machine-detail-dialog" :show-close="false" :close-on-press-escape="false">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="closeDetailDialog" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">机械详情</div>
        </div>
      </template>
      <el-descriptions :column="1" border class="machine-detail-card">
        <el-descriptions-item label="名称">{{ detailRow.name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="规格">{{ detailRow.spec || '-' }}</el-descriptions-item>
        <el-descriptions-item label="施工日期">{{ detailRow.use_date || '-' }}</el-descriptions-item>
        <el-descriptions-item label="台班">{{ detailRow.shift_count || '-' }}</el-descriptions-item>
        <el-descriptions-item label="备注">{{ detailRow.remark || '-' }}</el-descriptions-item>
      </el-descriptions>
      <div class="view-photos" v-if="detailPhotos.length">
        <div class="view-photos-title">现场照片</div>
        <div class="view-photos-grid">
          <div v-for="(photo, index) in detailPhotos" :key="photo.id" class="view-photo-item">
            <el-image
              class="view-photo-image"
              :src="photo.previewUrl"
              :preview-src-list="detailPhotoUrls"
              :initial-index="index"
              fit="cover"
              preview-teleported
              hide-on-click-modal
            />
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Delete, Download, Edit, Plus } from '@element-plus/icons-vue'
import api from '../api'
import { downloadByApi } from '../download'
import ToolbarSearchInput from '../components/ToolbarSearchInput.vue'
import ToolbarIconAction from '../components/ToolbarIconAction.vue'
import StockHeadBar from '../components/StockHeadBar.vue'
import { formatDateInput } from '../utils/date'
import { useRequestLatest } from '../composables/useRequestLatest'
import { useLoadGuard } from '../composables/useLoadGuard'

const allRows = ref([])
const keyword = ref('')
const page = ref(1)
const pageSize = 10
const rows = computed(() => allRows.value.slice((page.value - 1) * pageSize, (page.value - 1) * pageSize + pageSize))
const totalPages = computed(() => Math.max(1, Math.ceil(allRows.value.length / pageSize)))
const selectedIds = ref([])

const open = ref(false)
const editingId = ref(0)
const saving = ref(false)
const deleting = ref(false)
const form = reactive({ name: '', spec: '', use_date: '', shift_count: '', remark: '' })

const detailOpen = ref(false)
const detailId = ref(0)
const detailRow = reactive({ name: '', spec: '', use_date: '', shift_count: '', remark: '' })
const detailPhotos = ref([])
const detailPhotoUrls = ref([])
const detailRequest = useRequestLatest()
const listRequest = useRequestLatest()
const { loading: listLoading, run: runLoad } = useLoadGuard()

const photoFileList = ref([])
const originalPhotoIds = ref([])
const albumInputRef = ref(null)
const photoPreviewUrls = computed(() => photoFileList.value.map((item) => item.previewUrl).filter(Boolean))

const formatIndex = (index) => String(index + 1).padStart(2, '0')
const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const useDateInput = computed({
  get: () => form.use_date,
  set: (v) => {
    form.use_date = formatDateInput(v)
  }
})

const shiftCountInput = computed({
  get: () => `${form.shift_count ?? ''}`,
  set: (value) => {
    const cleaned = String(value || '')
      .replace(/[^\d.]/g, '')
      .replace(/\.(?=.*\.)/g, '')
    form.shift_count = cleaned
  }
})

const revokeObjectUrl = (url) => {
  if (url?.startsWith('blob:')) URL.revokeObjectURL(url)
}
const clearPhotoFiles = () => {
  photoFileList.value.forEach((i) => revokeObjectUrl(i.previewUrl))
  photoFileList.value = []
  originalPhotoIds.value = []
}
const clearDetailPhotos = () => {
  detailPhotos.value.forEach((i) => revokeObjectUrl(i.previewUrl))
  detailPhotos.value = []
  detailPhotoUrls.value = []
}
const loadAttachmentPreviewUrl = async (id) => {
  const { data } = await api.get(`/attachments/${id}/download`, { responseType: 'blob' })
  return URL.createObjectURL(data)
}

const load = async () => {
  const token = listRequest.next()
  await runLoad(
    async () => {
      const { data } = await api.get('/machine-ledger', { params: { keyword: keyword.value } })
      if (!listRequest.isLatest(token)) return
      allRows.value = data
      if (page.value > totalPages.value) page.value = totalPages.value
    },
    (e) => {
      if (!listRequest.isLatest(token)) return
      ElMessage.error(e.response?.data?.detail || '加载机械台账失败')
    }
  )
}

const download = async () => {
  await downloadByApi('/export/machine-ledger', 'machine-ledger.xls', { keyword: keyword.value })
}

const openCreateDialog = () => {
  editingId.value = 0
  form.name = ''
  form.spec = ''
  form.use_date = today()
  form.shift_count = ''
  form.remark = ''
  clearPhotoFiles()
  open.value = true
}
const closeCreateDialog = () => {
  open.value = false
  editingId.value = 0
  clearPhotoFiles()
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
  const target = photoFileList.value.find((i) => i.uid === uid)
  if (target) revokeObjectUrl(target.previewUrl)
  photoFileList.value = photoFileList.value.filter((i) => i.uid !== uid)
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

const save = async () => {
  if (saving.value) return
  if (!form.name.trim()) return ElMessage.error('请输入机械名称')
  saving.value = true
  try {
    const payload = {
      name: form.name,
      spec: form.spec,
      use_date: form.use_date,
      shift_count: Number(form.shift_count || 0),
      remark: form.remark
    }
    let rowId = 0
    if (editingId.value) {
      await api.put(`/machine-ledger/${editingId.value}`, payload)
      rowId = editingId.value
    } else {
      const { data } = await api.post('/machine-ledger', payload)
      rowId = Number(data?.id || 0)
    }
    for (const item of photoFileList.value) {
      if (!item.raw) continue
      await uploadPhotoWithRetry(rowId, item.raw, 2)
    }
    if (editingId.value) {
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
    ElMessage.success(editingId.value ? '更新成功' : '新增成功')
    closeCreateDialog()
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const editRow = async (row) => {
  editingId.value = Number(row.id || 0)
  form.name = row.name || ''
  form.spec = row.spec || ''
  form.use_date = row.use_date || today()
  form.shift_count = row.shift_count === '' || row.shift_count == null ? '' : `${row.shift_count}`
  form.remark = row.remark || ''
  clearPhotoFiles()
  try {
    const { data } = await api.get(`/attachments?order_type=machine_ledger&order_id=${editingId.value}`)
    originalPhotoIds.value = (data || []).map((a) => Number(a.id)).filter((id) => Number.isFinite(id) && id > 0)
    const files = await Promise.all((data || []).map(async (a, idx) => ({ uid: `existing-${idx}-${a.id}`, id: Number(a.id), name: a.filename, status: 'success', previewUrl: await loadAttachmentPreviewUrl(a.id) })))
    photoFileList.value = files
  } catch {
    originalPhotoIds.value = []
    photoFileList.value = []
  }
  open.value = true
}

const openDetailByRow = (row) => {
  const token = detailRequest.next()
  detailId.value = Number(row.id || 0)
  detailRow.name = row.name || ''
  detailRow.spec = row.spec || ''
  detailRow.use_date = row.use_date || ''
  detailRow.shift_count = row.shift_count || ''
  detailRow.remark = row.remark || ''
  loadDetailPhotos(token)
}
const loadDetailPhotos = async (token) => {
  clearDetailPhotos()
  try {
    const { data } = await api.get(`/attachments?order_type=machine_ledger&order_id=${detailId.value}`)
    if (!detailRequest.isLatest(token)) return
    const photos = await Promise.all((data || []).map(async (a) => ({ ...a, previewUrl: await loadAttachmentPreviewUrl(a.id) })))
    if (!detailRequest.isLatest(token)) {
      photos.forEach((item) => revokeObjectUrl(item.previewUrl))
      return
    }
    detailPhotos.value = photos
    detailPhotoUrls.value = photos.map((p) => p.previewUrl)
  } catch {
    if (!detailRequest.isLatest(token)) return
    detailPhotos.value = []
  }
  if (!detailRequest.isLatest(token)) return
  detailOpen.value = true
}
const closeDetailDialog = () => {
  detailRequest.invalidate()
  detailOpen.value = false
  detailId.value = 0
  clearDetailPhotos()
}

const onSelectionChange = (items) => {
  selectedIds.value = items.map((i) => i.id)
}
const deleteSelected = async () => {
  if (!selectedIds.value.length || deleting.value) return
  deleting.value = true
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 条机械台账吗？`, '删除确认', { type: 'warning' })
    await api.post('/machine-ledger/delete', { ids: selectedIds.value })
    ElMessage.success('删除成功')
    selectedIds.value = []
    await load()
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e.response?.data?.detail || '删除失败')
  } finally {
    deleting.value = false
  }
}
const prevPage = () => {
  if (page.value > 1) page.value -= 1
}
const nextPage = () => {
  if (page.value < totalPages.value) page.value += 1
}

onMounted(load)
onBeforeUnmount(() => {
  listRequest.invalidate()
  detailRequest.invalidate()
  clearPhotoFiles()
  clearDetailPhotos()
})
</script>

<style scoped>
.machine-form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 18px;
}
.machine-form-col { margin-bottom: 0; }
.machine-remark-item { margin-bottom: 18px; }

.machine-shift-input :deep(.el-input__inner),
.machine-ledger-dialog :deep(.el-input__inner),
.machine-ledger-dialog :deep(.el-input__inner::placeholder) {
  text-align: left !important;
}

.native-photo-input,
.photo-upload { display: none; }

.photo-upload-row {
  margin-top: 8px;
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
  flex: 0 0 auto;
}
.photo-add-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.photo-add-plus { font-size: 24px; line-height: 1; }

.photo-preview-list { display: flex; align-items: center; gap: 8px; }
.photo-preview-item {
  width: 82px;
  height: 82px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  background: var(--panel-solid);
  flex: 0 0 auto;
}
.photo-preview-image,
.photo-preview-image :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.remove-preview-btn {
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
}

.machine-detail-dialog :deep(.el-dialog__body) {
  background: var(--panel-solid);
}
.machine-detail-card :deep(.el-descriptions__body),
.machine-detail-card :deep(.el-descriptions__cell),
.machine-detail-card :deep(.el-descriptions__label) {
  background: var(--panel-solid) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
}
.machine-detail-card :deep(.el-descriptions__content) { color: var(--text) !important; }

.view-photos { margin-top: 14px; }
.view-photos-title { font-size: 12px; color: var(--text-subtle); margin-bottom: 8px; }
.view-photos-grid {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
}
.view-photo-item {
  width: 82px;
  height: 82px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--panel-solid);
  flex: 0 0 auto;
}
.view-photo-image,
.view-photo-image :deep(.el-image__inner) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
