<template>
  <div class="page-card module-page materials-manage-page">
    <StockHeadBar title="材料管理" :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage">
      <template #actions>
        <ToolbarSearchInput v-model="keyword" placeholder="按名称/规格搜索" @enter="load" />
        <ToolbarIconAction tooltip="新增材料" aria-label="新增材料" @click="resetForm">
          <Plus />
        </ToolbarIconAction>
        <ToolbarIconAction tooltip="删除选中" aria-label="删除选中" type="danger" :disabled="!selectedIds.length" @click="deleteSelected">
          <Delete />
        </ToolbarIconAction>
      </template>
    </StockHeadBar>

    <el-table v-loading="listLoading" class="uniform-row-table clickable-table" :data="rows" border @selection-change="onSelectionChange" @row-click="onRowClick">
      <el-table-column type="selection" width="50" />
      <el-table-column label="序号" width="70">
        <template #default="scope">
          {{ formatIndex(scope.$index) }}
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="spec" label="规格" min-width="180" />
      <el-table-column prop="unit" label="单位" width="100" />
    </el-table>


    <el-dialog v-model="open" width="min(500px, 90vw)" class="macos-dialog materials-dialog" :show-close="false" :close-on-press-escape="false" @keydown.enter.prevent="save">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="open = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">{{ editingId ? '编辑材料' : '新增材料' }}</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="保存" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="保存" @click="save">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <el-form label-width="0" @keydown.enter.prevent="save">
        <el-form-item>
          <el-input v-model="form.name" placeholder="请输入名称" />
        </el-form-item>
        <el-form-item>
          <el-input
            ref="specInputRef"
            v-model="form.spec"
            placeholder="请输入规格（输入助记码后按 Tab 快速插入符号）"
            @click="captureSpecCursor"
            @keyup="captureSpecCursor"
            @keydown="onSpecInputKeydown"
          >
            <template #append>
              <el-dropdown
                trigger="click"
                placement="bottom"
                :teleported="true"
                :popper-options="templatePopperOptions"
                :popper-style="specDropdownPopperStyle"
                popper-class="materials-template-popper materials-template-popper--spec"
                @visible-change="onSpecDropdownVisibleChange"
                @command="insertSpecSymbol"
              >
                <span>符号模板</span>
                <template #dropdown>
                  <el-dropdown-menu class="materials-template-menu materials-template-menu--spec">
                    <el-dropdown-item
                      v-for="item in specSymbolTemplates"
                      :key="`${item.symbol}-${item.code}`"
                      :command="item.symbol"
                    >
                      {{ item.symbol }} {{ item.code }} {{ item.label }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-input ref="unitInputRef" v-model="form.unit" placeholder="请输入单位">
            <template #append>
              <el-dropdown trigger="click" @command="insertUnitTemplate">
                <span>单位模板</span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="unit in commonUnitOptions" :key="unit" :command="unit">
                      {{ unit }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-input>
        </el-form-item>
      </el-form>
    </el-dialog>

  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Delete, Plus } from '@element-plus/icons-vue'
import api from '../api'
import ToolbarSearchInput from '../components/ToolbarSearchInput.vue'
import ToolbarIconAction from '../components/ToolbarIconAction.vue'
import StockHeadBar from '../components/StockHeadBar.vue'
import { usePagedApiList } from '../composables/usePagedApiList'

const keyword = ref('')
const selectedPageSize = 10
const selectedIds = ref([])
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
  errorMessage: '加载材料失败',
  fetchPage: ({ page, pageSize }) => api.get('/materials', { params: { keyword: keyword.value, page, page_size: pageSize } }),
  onLoadSuccess: () => {
    selectedIds.value = []
  }
})

const formatIndex = (index) => String((page.value - 1) * selectedPageSize + index + 1).padStart(2, '0')
const open = ref(false)
const editingId = ref(0)
const form = reactive({ name: '', spec: '', unit: '' })
const specInputRef = ref(null)
const unitInputRef = ref(null)
const commonUnitOptions = ['台', '米', '个', '片']

const specSymbolTemplates = [
  { symbol: '⌀', code: 'd', label: '标准直径符号' },
  { symbol: '×', code: 'x', label: '乘号/数量' },
  { symbol: '±', code: 'zf', label: '正负号/公差' },
  { symbol: '°', code: 'du', label: '度数/角度' },
  { symbol: '²', code: 'pf', label: '平方' },
  { symbol: '³', code: 'lf', label: '立方' },
  { symbol: '∠', code: 'jg', label: '角钢(图形符号)' },
  { symbol: 'L', code: 'jg', label: '角钢(字母符号)' },
  { symbol: '[', code: 'cg', label: '槽钢' },
  { symbol: '工', code: 'gzg', label: '工字钢' },
  { symbol: 'H', code: 'hxg', label: 'H型钢' },
  { symbol: '□', code: 'fg', label: '方钢/方管(空心)' },
  { symbol: '■', code: 'fg', label: '实心方钢' },
  { symbol: '○', code: 'yg', label: '圆钢/圆管(空心)' },
  { symbol: '●', code: 'yg', label: '实心圆钢' },
  { symbol: '—', code: 'bg', label: '扁钢/扁铁' },
  { symbol: 'δ', code: 'hd', label: '厚度' },
  { symbol: 'DN', code: 'gj', label: '公称直径' }
]

const specShortcutMap = specSymbolTemplates.reduce((acc, item) => {
  if (!acc[item.code]) {
    acc[item.code] = item.symbol
  }
  return acc
}, {})

const templatePopperOptions = {
  strategy: 'absolute',
  modifiers: [
    {
      name: 'offset',
      options: {
        offset: [0, 0]
      }
    },
    {
      name: 'preventOverflow',
      options: {
        boundary: 'viewport',
        padding: 8
      }
    }
  ]
}

const specDropdownVisible = ref(false)
const specDropdownPopperStyle = ref({})

const updateSpecDropdownPosition = () => {
  if (!specDropdownVisible.value) return
  const dialogEl = document.querySelector('.materials-dialog.el-dialog')
  const specInputEl = specInputRef.value?.$el
  if (!dialogEl || !specInputEl) return
  const dialogRect = dialogEl.getBoundingClientRect()
  const inputRect = specInputEl.getBoundingClientRect()
  const viewportPadding = 8
  const maxAllowedWidth = Math.max(280, window.innerWidth - viewportPadding * 2)
  const nextWidth = Math.min(Math.max(280, dialogRect.width - 24), Math.min(860, maxAllowedWidth))
  const top = Math.min(window.innerHeight - viewportPadding, inputRect.bottom)
  const availableHeight = Math.max(180, window.innerHeight - top - viewportPadding)
  const itemApproxHeight = 40
  const minColWidth = 180
  const maxColsByWidth = Math.max(1, Math.floor((nextWidth - 16) / minColWidth))
  const rowsByHeight = Math.max(1, Math.floor((availableHeight - 16) / itemApproxHeight))
  const neededCols = Math.max(1, Math.ceil(specSymbolTemplates.length / rowsByHeight))
  const resolvedCols = Math.min(maxColsByWidth, neededCols)
  const centerX = dialogRect.left + dialogRect.width / 2
  specDropdownPopperStyle.value = {
    position: 'fixed',
    left: `${centerX}px`,
    top: `${top}px`,
    transform: 'translateX(-50%)',
    width: `${nextWidth}px`,
    '--spec-cols': `${resolvedCols}`,
    '--spec-menu-max-height': `${availableHeight}px`
  }
}

const onSpecDropdownVisibleChange = (visible) => {
  specDropdownVisible.value = visible
  if (!visible) return
  nextTick(() => {
    updateSpecDropdownPosition()
  })
}

const getSpecNativeInput = () => specInputRef.value?.input || null
const getUnitNativeInput = () => unitInputRef.value?.input || null

const captureSpecCursor = (event) => {
  const target = event?.target
  if (!target || typeof target.selectionStart !== 'number') return
  target.dataset.cursor = String(target.selectionStart)
}

const insertSpecSymbol = (symbol) => {
  const input = getSpecNativeInput()
  const start = input?.selectionStart ?? form.spec.length
  const end = input?.selectionEnd ?? start
  form.spec = `${form.spec.slice(0, start)}${symbol}${form.spec.slice(end)}`
  nextTick(() => {
    const currentInput = getSpecNativeInput()
    if (!currentInput) return
    const cursor = start + symbol.length
    currentInput.focus()
    currentInput.setSelectionRange(cursor, cursor)
  })
}

const onSpecInputKeydown = (event) => {
  if (event.key !== 'Tab') return

  const input = getSpecNativeInput()
  if (!input || typeof input.selectionStart !== 'number' || input.selectionStart !== input.selectionEnd) return

  const cursor = input.selectionStart
  const leftText = form.spec.slice(0, cursor)
  const matched = leftText.match(/([A-Za-z]+)$/)
  if (!matched) return

  const code = matched[1].toLowerCase()
  const symbol = specShortcutMap[code]
  if (!symbol) return

  event.preventDefault()
  const start = cursor - matched[1].length
  form.spec = `${form.spec.slice(0, start)}${symbol}${form.spec.slice(cursor)}`

  nextTick(() => {
    const currentInput = getSpecNativeInput()
    if (!currentInput) return
    const nextCursor = start + symbol.length
    currentInput.focus()
    currentInput.setSelectionRange(nextCursor, nextCursor)
  })
}

const insertUnitTemplate = (unit) => {
  const input = getUnitNativeInput()
  const start = input?.selectionStart ?? form.unit.length
  const end = input?.selectionEnd ?? start
  form.unit = `${form.unit.slice(0, start)}${unit}${form.unit.slice(end)}`

  nextTick(() => {
    const currentInput = getUnitNativeInput()
    if (!currentInput) return
    const cursor = start + unit.length
    currentInput.focus()
    currentInput.setSelectionRange(cursor, cursor)
  })
}

const onSelectionChange = (selection) => {
  selectedIds.value = selection.map((item) => item.id)
}

const onRowClick = (row, column) => {
  if (!column || column.type === 'selection') return
  if (selectedIds.value.includes(row.id)) return
  editingId.value = row.id
  Object.assign(form, {
    name: row.name || '',
    spec: row.spec || '',
    unit: row.unit || ''
  })
  open.value = true
}

const resetForm = () => {
  editingId.value = 0
  Object.assign(form, { name: '', spec: '', unit: '' })
  open.value = true
}

const save = async () => {
  try {
    if (editingId.value) {
      await api.put(`/materials/${editingId.value}`, form)
      ElMessage.success('保存成功')
      open.value = false
      editingId.value = 0
    } else {
      await api.post('/materials', form)
      ElMessage.success('添加成功')
      Object.assign(form, { name: '', spec: '', unit: '' })
    }
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

const deleteSelected = async () => {
  if (!selectedIds.value.length) return
  try {
    await api.post('/materials/delete', { material_ids: selectedIds.value })
    ElMessage.success('删除成功')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const resetMaterialsPage = async () => {
  resetPage()
  keyword.value = ''
  open.value = false
  editingId.value = 0
  Object.assign(form, { name: '', spec: '', unit: '' })
  await load()
}

const onResetEvent = () => {
  resetMaterialsPage()
}

const onCloseAllDialogs = () => {
  open.value = false
}

const onWindowResize = () => {
  updateSpecDropdownPosition()
}

onMounted(() => {
  window.addEventListener('reset-current-page', onResetEvent)
  window.addEventListener('close-all-dialogs', onCloseAllDialogs)
  window.addEventListener('resize', onWindowResize)
  load()
})

onBeforeUnmount(() => {
  invalidate()
  window.removeEventListener('close-all-dialogs', onCloseAllDialogs)
  window.removeEventListener('reset-current-page', onResetEvent)
  window.removeEventListener('resize', onWindowResize)
})
</script>

<style>
.materials-template-popper {
  max-width: 94vw;
}

.materials-template-popper .el-dropdown-menu {
  min-width: 100% !important;
  max-height: var(--spec-menu-max-height, min(70vh, 520px));
  overflow: auto;
  padding: 8px;
}

.materials-template-popper .el-dropdown-menu__item {
  white-space: normal;
  line-height: 1.4;
  min-height: 34px;
  height: auto;
  border-radius: 8px;
}

.materials-template-popper .materials-template-menu {
  display: grid;
  gap: 4px;
  align-items: stretch;
}

.materials-template-popper .materials-template-menu--spec {
  grid-template-columns: repeat(var(--spec-cols, 2), minmax(0, 1fr));
}

.materials-template-popper .materials-template-menu--unit {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (min-width: 1200px) {
  .materials-template-popper .materials-template-menu--unit {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (min-width: 1600px) {
  .materials-template-popper .materials-template-menu--unit {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .materials-template-popper {
    max-width: 92vw;
  }

  .materials-template-popper .el-dropdown-menu {
    min-width: 92vw !important;
    max-height: 62vh;
    overflow-y: auto;
  }

  .materials-template-popper .materials-template-menu--spec {
    grid-template-columns: 1fr;
  }

  .materials-template-popper .materials-template-menu--unit {
    grid-template-columns: 1fr;
  }
}
</style>
