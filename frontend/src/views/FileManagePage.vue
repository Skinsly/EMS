<template>
  <div class="page-card module-page file-manage-page">
    <StockHeadBar :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage">
      <template #actions>
        <div class="file-action-search">
          <ToolbarSearchInput v-model="keyword" placeholder="按文件名/备注搜索" @enter="loadFiles" />
        </div>
        <div class="file-action-upload">
          <ToolbarIconAction tooltip="上传文件" aria-label="上传文件" type="primary" @click="openUploadDialog">
            <Upload />
          </ToolbarIconAction>
        </div>
        <div class="file-action-add">
          <ToolbarIconAction tooltip="新增分类" aria-label="新增分类" @click="createCategory">
            <Plus />
          </ToolbarIconAction>
        </div>
        <div class="file-action-rename">
          <ToolbarIconAction tooltip="重命名分类" aria-label="重命名分类" :disabled="!activeCategory" @click="renameCategory">
            <Edit />
          </ToolbarIconAction>
        </div>
        <div class="file-action-delete">
          <ToolbarIconAction tooltip="删除分类" aria-label="删除分类" type="danger" :disabled="!activeCategory" @click="deleteCategory">
            <Delete />
          </ToolbarIconAction>
        </div>
      </template>
      <template #title>
        <div class="file-title-select">
          <el-dropdown trigger="click" popper-class="file-category-select-popper" @command="onTitleCategoryCommand">
            <button type="button" class="file-title-trigger" aria-label="选择分类">
              <span class="file-title-text">{{ categoryTitleLabel }}</span>
              <el-icon class="file-title-arrow"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="">全部分类</el-dropdown-item>
                <el-dropdown-item v-for="item in categories" :key="item.id" :command="String(item.id)">
                  {{ item.name }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>
    </StockHeadBar>

    <el-table class="uniform-row-table" :data="rows" border>
      <el-table-column label="序号" width="70">
        <template #default="scope">{{ formatIndex(scope.$index) }}</template>
      </el-table-column>
      <el-table-column prop="category_name" label="分类" width="140" />
      <el-table-column prop="filename" label="文件名" min-width="240" show-overflow-tooltip />
      <el-table-column prop="size" label="大小" width="110">
        <template #default="scope">{{ formatSize(scope.row.size) }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="上传时间" width="170">
        <template #default="scope">{{ formatDate(scope.row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-button link type="primary" @click="previewFile(scope.row)">预览</el-button>
          <el-button link type="primary" @click="downloadFile(scope.row)">下载</el-button>
          <el-tooltip content="删除文件" placement="bottom">
            <el-button link type="danger" @click="removeFile(scope.row)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="uploadOpen"
      width="min(520px, 92vw)"
      class="macos-dialog"
      :show-close="false"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
    >
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" :disabled="uploading" @click="uploadOpen = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">上传文件</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="确认" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="确认" :disabled="uploading" @click="submitUpload">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>

      <el-form label-width="0" @keydown.enter.prevent="submitUpload">
        <el-form-item>
          <el-select v-model="uploadForm.category_id" style="width: 100%" placeholder="请选择分类" popper-class="file-category-select-popper">
            <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-input v-model="uploadForm.remark" placeholder="备注（可选）" maxlength="255" />
        </el-form-item>
        <el-form-item>
          <input ref="uploadInputRef" class="native-file-input" type="file" accept="image/*,.pdf" @change="onPickedFile" />
          <div class="picked-file-name">{{ pickedFileName || '未选择文件' }}</div>
          <el-tooltip content="选择文件" placement="bottom">
            <button class="dialog-save-plus-btn" type="button" aria-label="选择文件" :disabled="uploading" @click="pickFile">
              <el-icon><Upload /></el-icon>
            </button>
          </el-tooltip>
        </el-form-item>
      </el-form>
    </el-dialog>

    <el-dialog v-model="createCategoryOpen" width="min(460px, 90vw)" class="macos-dialog" :show-close="false" :close-on-press-escape="false">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="createCategoryOpen = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">新增分类</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="确认" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="确认" @click="submitCreateCategory">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <el-form label-width="0" @keydown.enter.prevent="submitCreateCategory">
        <el-form-item>
          <el-input v-model="createCategoryName" maxlength="64" placeholder="请输入分类名称" />
        </el-form-item>
      </el-form>
    </el-dialog>

    <el-dialog v-model="renameCategoryOpen" width="min(460px, 90vw)" class="macos-dialog" :show-close="false" :close-on-press-escape="false">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="renameCategoryOpen = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">重命名分类</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="确认" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="确认" @click="submitRenameCategory">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <el-form label-width="0" @keydown.enter.prevent="submitRenameCategory">
        <el-form-item>
          <el-input v-model="renameCategoryName" maxlength="64" placeholder="请输入新的分类名称" />
        </el-form-item>
      </el-form>
    </el-dialog>

    <el-dialog v-model="deleteCategoryOpen" width="min(500px, 90vw)" class="macos-dialog" :show-close="false" :close-on-press-escape="false">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="deleteCategoryOpen = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">删除分类</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="确认" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="确认" :disabled="deletingCategory" @click="submitDeleteCategory">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <el-form label-width="0" @keydown.enter.prevent="submitDeleteCategory">
        <el-form-item>
          <div class="delete-category-tip">将删除分类“{{ activeCategory?.name || '-' }}”，请输入登录密码确认。</div>
        </el-form-item>
        <el-form-item>
          <div class="delete-category-count">当前分类文件数：{{ deleteCategoryFileCount }}</div>
        </el-form-item>
        <el-form-item>
          <el-input v-model="deleteCategoryPassword" show-password placeholder="请输入当前登录密码" />
        </el-form-item>
        <el-form-item v-if="deleteCategoryNeedConfirm">
          <el-alert :title="deleteCategoryWarning" type="warning" :closable="false" />
        </el-form-item>
        <el-form-item v-if="deleteCategoryNeedConfirm">
          <el-checkbox v-model="deleteCategoryConfirmed">我已确认删除该分类下全部文件</el-checkbox>
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { ArrowDown, Check, Delete, Edit, Plus, Upload } from '@element-plus/icons-vue'
import api from '../api'
import { downloadByApi } from '../download'
import StockHeadBar from '../components/StockHeadBar.vue'
import ToolbarIconAction from '../components/ToolbarIconAction.vue'
import ToolbarSearchInput from '../components/ToolbarSearchInput.vue'
import { usePagedApiList } from '../composables/usePagedApiList'
import { notify } from '../utils/notify'

const categories = ref([])
const categoryFilter = ref('')
const keyword = ref('')
const allRows = ref([])
const selectedPageSize = 10
const uploadOpen = ref(false)
const uploading = ref(false)
const uploadInputRef = ref(null)
const pickedFile = ref(null)
const uploadForm = reactive({ category_id: '', remark: '' })
const createCategoryOpen = ref(false)
const renameCategoryOpen = ref(false)
const createCategoryName = ref('')
const renameCategoryName = ref('')
const deleteCategoryOpen = ref(false)
const deleteCategoryPassword = ref('')
const deleteCategoryNeedConfirm = ref(false)
const deleteCategoryConfirmed = ref(false)
const deleteCategoryWarning = ref('')
const deletingCategory = ref(false)
const searchTimer = ref(0)
const {
  page,
  totalPages,
  load: loadFiles,
  prevPage,
  nextPage,
  resetPage,
  invalidate
} = usePagedApiList({
  pageSize: selectedPageSize,
  errorMessage: '加载文件列表失败',
  fetchPage: ({ page, pageSize }) => {
    const params = { keyword: keyword.value, page, page_size: pageSize }
    if (categoryFilter.value) {
      params.category_id = categoryFilter.value
    }
    return api.get('/project-files', { params })
  },
  onLoadSuccess: (data) => {
    allRows.value = Array.isArray(data?.items) ? data.items : []
  }
})

const activeCategory = computed(() => categories.value.find((item) => String(item.id) === String(categoryFilter.value)) || null)
const categoryTitleLabel = computed(() => activeCategory.value?.name || '全部分类')
const rows = computed(() => allRows.value)
const pickedFileName = computed(() => pickedFile.value?.name || '')
const deleteCategoryFileCount = computed(() => {
  if (!activeCategory.value) return 0
  return Number(activeCategory.value.file_count || 0)
})

const formatIndex = (index) => String((page.value - 1) * selectedPageSize + index + 1).padStart(2, '0')
const formatDate = (text) => String(text || '').replace('T', ' ').slice(0, 19)
const formatSize = (size) => {
  const n = Number(size || 0)
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

const resetUploadForm = () => {
  uploadForm.category_id = categoryFilter.value || categories.value[0]?.id || ''
  uploadForm.remark = ''
  pickedFile.value = null
  if (uploadInputRef.value) uploadInputRef.value.value = ''
}

const loadCategories = async () => {
  const { data } = await api.get('/file-categories')
  categories.value = data || []
  if (!categories.value.length) {
    categoryFilter.value = ''
  } else if (categoryFilter.value && !categories.value.some((item) => String(item.id) === String(categoryFilter.value))) {
    categoryFilter.value = ''
  }
}

const onFilterChange = () => {
  resetPage()
  loadFiles()
}

const onKeywordInput = () => {
  if (searchTimer.value) {
    window.clearTimeout(searchTimer.value)
  }
  searchTimer.value = window.setTimeout(() => {
    resetPage()
    loadFiles()
  }, 300)
}

const onTitleCategoryCommand = (value) => {
  categoryFilter.value = value || ''
  onFilterChange()
}

const openUploadDialog = () => {
  resetUploadForm()
  uploadOpen.value = true
}

const pickFile = () => {
  uploadInputRef.value?.click()
}

const onPickedFile = (event) => {
  const file = event.target.files?.[0]
  pickedFile.value = file || null
}

const submitUpload = async () => {
  if (uploading.value) return
  if (!uploadForm.category_id) return notify.error('请选择分类')
  if (!pickedFile.value) return notify.error('请选择文件')
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', pickedFile.value)
    await api.post('/project-files/upload', fd, {
      params: {
        category_id: uploadForm.category_id,
        remark: uploadForm.remark || ''
      }
    })
    notify.success('上传成功')
    resetUploadForm()
    uploadOpen.value = false
    await loadFiles()
  } catch (e) {
    notify.error(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

const createCategory = async () => {
  createCategoryName.value = ''
  createCategoryOpen.value = true
}

const submitCreateCategory = async () => {
  const name = createCategoryName.value.trim()
  if (!name) return notify.error('分类名称不能为空')
  try {
    await api.post('/file-categories', { name })
    notify.success('分类已新增')
    createCategoryOpen.value = false
    await loadCategories()
  } catch (e) {
    notify.error(e.response?.data?.detail || '新增分类失败')
  }
}

const renameCategory = async () => {
  if (!activeCategory.value) return
  renameCategoryName.value = activeCategory.value.name || ''
  renameCategoryOpen.value = true
}

const submitRenameCategory = async () => {
  if (!activeCategory.value) return
  const name = renameCategoryName.value.trim()
  if (!name) return notify.error('分类名称不能为空')
  try {
    await api.put(`/file-categories/${activeCategory.value.id}`, { name })
    notify.success('分类已重命名')
    renameCategoryOpen.value = false
    await loadCategories()
    await loadFiles()
  } catch (e) {
    notify.error(e.response?.data?.detail || '分类重命名失败')
  }
}

const deleteCategory = async () => {
  if (!activeCategory.value) return
  deleteCategoryPassword.value = ''
  deleteCategoryNeedConfirm.value = false
  deleteCategoryConfirmed.value = false
  deleteCategoryWarning.value = ''
  deleteCategoryOpen.value = true
}

const submitDeleteCategory = async () => {
  if (!activeCategory.value || deletingCategory.value) return
  const password = deleteCategoryPassword.value.trim()
  if (!password) return notify.error('请输入登录密码')
  if (deleteCategoryNeedConfirm.value && !deleteCategoryConfirmed.value) {
    return notify.error('请先确认删除该分类下全部文件')
  }

  deletingCategory.value = true
  try {
    await api.delete(`/file-categories/${activeCategory.value.id}`, {
      data: {
        password,
        delete_files_confirmed: deleteCategoryNeedConfirm.value && deleteCategoryConfirmed.value
      }
    })
    notify.success(deleteCategoryNeedConfirm.value ? '分类及内部文件已删除' : '分类已删除')
    deleteCategoryOpen.value = false
    if (String(categoryFilter.value) === String(activeCategory.value.id)) {
      categoryFilter.value = ''
    }
    await loadCategories()
    await loadFiles()
  } catch (e) {
    const detail = String(e.response?.data?.detail || '')
    if (detail.includes('请确认是否一并删除')) {
      deleteCategoryNeedConfirm.value = true
      deleteCategoryWarning.value = detail
      return notify.warning('该分类下有文件，请勾选确认后再次提交')
    }
    notify.error(detail || '删除分类失败')
  } finally {
    deletingCategory.value = false
  }
}

const removeFile = async (row) => {
  try {
    await ElMessageBox.confirm(`删除文件“${row.filename}”后不可恢复，是否继续？`, '删除确认', { type: 'warning' })
    await api.delete(`/project-files/${row.id}`)
    notify.success('文件已删除')
    await loadFiles()
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    notify.error(e.response?.data?.detail || '删除文件失败')
  }
}

const downloadFile = async (row) => {
  try {
    await downloadByApi(`/project-files/${row.id}/download`, row.filename)
  } catch (e) {
    notify.error(e.response?.data?.detail || '下载失败')
  }
}

const previewFile = (row) => {
  api
    .get(`/project-files/${row.id}/preview`, { responseType: 'blob' })
    .then((res) => {
      const url = window.URL.createObjectURL(res.data)
      window.open(url, '_blank', 'noopener')
      window.setTimeout(() => window.URL.revokeObjectURL(url), 60000)
    })
    .catch((e) => {
      notify.error(e.response?.data?.detail || '预览失败')
    })
}

onMounted(async () => {
  await loadCategories()
  await loadFiles()
})

watch(keyword, () => {
  onKeywordInput()
})

onBeforeUnmount(() => {
  invalidate()
  if (searchTimer.value) {
    window.clearTimeout(searchTimer.value)
  }
})
</script>

<style scoped>
.file-title-select {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  overflow: visible;
}

.file-title-select :deep(.el-dropdown) {
  height: 100%;
}

.file-title-trigger {
  position: relative;
  min-width: 0;
  height: 100%;
  border: none;
  background: transparent;
  color: var(--page-title-tip-text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  cursor: pointer;
  overflow: visible;
}

.file-title-text {
  color: var(--page-title-tip-text);
  font-weight: 600;
  font-size: 14px;
  line-height: 1;
}

.file-title-arrow {
  position: absolute;
  left: 50%;
  bottom: 0;
  transform: translate(-50%, 50%);
  font-size: 11px;
  color: color-mix(in oklab, var(--page-title-tip-text) 78%, var(--muted) 22%);
  pointer-events: none;
  z-index: 3;
}

.file-manage-page :deep(.stock-page-head .stock-page-title) {
  border-color: var(--page-title-tip-border);
  background: linear-gradient(145deg, var(--page-title-tip-bg-start), var(--page-title-tip-bg-end));
  color: var(--page-title-tip-text);
  box-shadow: var(--page-title-tip-shadow);
  overflow: visible;
  text-overflow: clip;
  cursor: pointer;
}

.file-manage-page :deep(.stock-page-head) {
  overflow: visible;
}

.native-file-input {
  display: none;
}

.picked-file-name {
  flex: 1;
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  color: var(--muted);
}

.delete-category-tip {
  width: 100%;
  color: var(--text);
  line-height: 1.6;
}

.delete-category-count {
  width: 100%;
  color: var(--muted);
  font-size: 12px;
}

:deep(.file-category-select-popper.el-popper) {
  background: linear-gradient(145deg, var(--page-title-tip-bg-start), var(--page-title-tip-bg-end));
  border: 1px solid var(--page-title-tip-border);
  box-shadow: var(--page-title-tip-shadow);
  border-radius: 14px;
  color: var(--page-title-tip-text);
}

:deep(.file-category-select-popper.el-popper .el-popper__arrow::before) {
  background: linear-gradient(145deg, var(--page-title-tip-bg-start), var(--page-title-tip-bg-end));
  border: 1px solid var(--page-title-tip-border);
}

:deep(.file-category-select-popper .el-select-dropdown__item) {
  color: var(--page-title-tip-text);
  background: transparent;
}

:deep(.file-category-select-popper .el-select-dropdown__item.hover),
:deep(.file-category-select-popper .el-select-dropdown__item:hover) {
  background: color-mix(in oklab, var(--accent) 18%, var(--surface-2) 82%) !important;
  color: var(--text) !important;
}

:deep(.file-category-select-popper .el-select-dropdown__item.selected) {
  background: color-mix(in oklab, var(--accent) 26%, var(--surface-2) 74%) !important;
  color: var(--text) !important;
}

:deep(.file-category-select-popper .el-dropdown-menu__item) {
  color: var(--page-title-tip-text);
  border-radius: 10px;
  margin: 2px 0;
  min-height: 32px;
}

:deep(.file-category-select-popper .el-dropdown-menu__item:not(.is-disabled):hover),
:deep(.file-category-select-popper .el-dropdown-menu__item:not(.is-disabled):focus) {
  background: color-mix(in oklab, var(--page-title-tip-text) 14%, transparent) !important;
  color: var(--page-title-tip-text) !important;
}

:deep(.file-category-select-popper .el-dropdown-menu) {
  border: none;
  box-shadow: none;
  background: transparent;
  padding: 6px;
}

@media (max-width: 900px) {
  .file-manage-page :deep(.stock-page-head) {
    grid-template-columns: var(--control-height-mobile) var(--control-height-mobile) minmax(0, 1fr) var(--control-height-mobile) var(--control-height-mobile);
    grid-template-areas:
      'upload del title add rename'
      'search search search pager pager';
    column-gap: 4px;
    row-gap: 8px;
  }

  .file-manage-page :deep(.stock-page-head .stock-head-actions) {
    display: contents !important;
  }

  .file-manage-page :deep(.stock-page-head .stock-page-title) {
    grid-area: title;
    margin: 0;
    justify-self: center;
    align-self: center;
  }

  .file-manage-page :deep(.stock-page-head .stock-head-actions .file-action-search) {
    grid-area: search !important;
    justify-self: start !important;
    width: var(--mobile-search-width) !important;
    min-width: var(--mobile-search-min-width) !important;
    max-width: var(--mobile-search-width) !important;
  }

  .file-manage-page :deep(.stock-page-head .stock-head-actions .file-action-search .toolbar-search-input),
  .file-manage-page :deep(.stock-page-head .stock-head-actions .file-action-search .el-input) {
    width: 100% !important;
    min-width: 100% !important;
    max-width: 100% !important;
  }

  .file-manage-page :deep(.stock-page-head .stock-head-actions .file-action-upload) {
    grid-area: upload !important;
    justify-self: start;
  }

  .file-manage-page :deep(.stock-page-head .stock-head-actions .file-action-delete) {
    grid-area: del !important;
    justify-self: start;
  }

  .file-manage-page :deep(.stock-page-head .stock-head-actions .file-action-add) {
    grid-area: add !important;
    justify-self: end;
  }

  .file-manage-page :deep(.stock-page-head .stock-head-actions .file-action-rename) {
    grid-area: rename !important;
    justify-self: end;
  }

  .file-manage-page :deep(.stock-page-head .top-pager) {
    grid-area: pager;
    justify-self: end;
    width: auto;
    display: inline-grid;
    grid-template-columns: var(--control-height-mobile) auto var(--control-height-mobile);
  }
}
</style>
