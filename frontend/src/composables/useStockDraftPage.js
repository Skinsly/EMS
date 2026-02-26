import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import { formatDateInput } from '../utils/date'

const QUICK_STOCK_DRAFT_KEY = 'quick-stock-draft'

const normalizeQty = (value) => {
  if (value === '' || value === null || typeof value === 'undefined') return ''
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return ''
  const fixed = Math.round(Math.max(0.001, parsed) * 1000) / 1000
  return Number.isInteger(fixed) ? String(fixed) : fixed.toFixed(3).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')
}

export const useStockDraftPage = (mode) => {
  const isOut = mode === 'out'
  const route = useRoute()
  const router = useRouter()
  const materials = ref([])
  const keyword = ref('')
  const isManageRoute = computed(() => route.path === '/stock-manage')
  const modeOptions = [
    { label: '入库', value: 'in' },
    { label: '出库', value: 'out' }
  ]
  const activeMode = computed({
    get: () => (route.query.mode === 'out' ? 'out' : 'in'),
    set: (value) => {
      router.replace({ path: '/stock-manage', query: { mode: value === 'out' ? 'out' : 'in' } })
    }
  })

  const onModeChange = (value) => {
    activeMode.value = value
  }

  const today = () => {
    const d = new Date()
    const yyyy = d.getFullYear()
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    return `${yyyy}-${mm}-${dd}`
  }

  const createEmptyRow = () => ({
    date: today(),
    material_id: null,
    qty: null,
    remark: ''
  })

  const rows = ref([])
  const addDialogOpen = ref(false)
  const draftRow = ref(createEmptyRow())
  const draftDateInput = computed({
    get: () => draftRow.value.date,
    set: (value) => {
      draftRow.value.date = formatDateInput(value)
    }
  })
  const draftMaterialText = ref('')
  const materialFieldRef = ref(null)
  const materialSuggestOpen = ref(false)
  const materialSuggestLeft = ref(12)
  const selectedRows = ref([])
  const editingRowIndex = ref(-1)
  const draftSaving = ref(false)
  const draftSavedAt = ref('')
  const commitLoading = ref(false)
  const draftDirty = ref(false)
  const lastSavedDraftPayload = ref('[]')
  const page = ref(1)
  const pageSize = 10
  let draftSaveTimer = null

  const formatIndex = (index) => String(index + 1).padStart(2, '0')

  const draftStatusText = computed(() => {
    if (commitLoading.value) return '正在入账...'
    if (draftSaving.value) return '草稿保存中...'
    if (!rows.value.length) return isOut ? '暂无待出账草稿' : '暂无待入账草稿'
    if (draftSavedAt.value) return `草稿已保存（${draftSavedAt.value}），待入账 ${rows.value.length} 条`
    return `待入账 ${rows.value.length} 条`
  })

  const filteredRows = computed(() => {
    const kw = keyword.value.trim().toLowerCase()
    return !kw
      ? rows.value
      : rows.value.filter((row) => {
          const m = getMaterial(row.material_id)
          const text = `${m?.name || ''} ${m?.spec || ''}`.toLowerCase()
          return text.includes(kw)
        })
  })

  const pagedRows = computed(() => {
    const start = (page.value - 1) * pageSize
    return filteredRows.value.slice(start, start + pageSize)
  })

  const totalPages = computed(() => {
    return Math.max(1, Math.ceil(filteredRows.value.length / pageSize))
  })

  const materialMap = computed(() => new Map(materials.value.map((m) => [Number(m.id), m])))
  const getMaterial = (materialId) => materialMap.value.get(Number(materialId))

  const setDraftMaterial = (materialId) => {
    const id = Number(materialId)
    draftRow.value.material_id = id
    const matched = getMaterial(id)
    draftMaterialText.value = matched ? `${matched.name} ${matched.spec || ''}`.trim() : ''
    materialSuggestOpen.value = false
  }

  const draftMaterialSuggestions = computed(() => {
    const kw = `${draftMaterialText.value || ''}`.trim().toLowerCase()
    if (!kw) return []
    return materials.value
      .map((m) => ({
        value: `${m.name} ${m.spec || ''}`.trim(),
        label: `${m.name} ${m.spec || ''}`.trim(),
        id: m.id
      }))
      .filter((item) => !kw || item.label.toLowerCase().includes(kw))
      .slice(0, 20)
  })

  const updateMaterialSuggestLeft = () => {
    const wrap = materialFieldRef.value
    if (!wrap) return

    const inputEl = wrap.querySelector('input')
    if (!inputEl) return

    const textBeforeCaret = inputEl.value.slice(0, inputEl.selectionStart || 0)
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const style = window.getComputedStyle(inputEl)
    const font = [style.fontStyle, style.fontVariant, style.fontWeight, style.fontSize, style.fontFamily].join(' ')
    ctx.font = font

    const paddingLeft = Number.parseFloat(style.paddingLeft || '0') || 0
    const measuredWidth = ctx.measureText(textBeforeCaret).width
    const inputOffset = inputEl.offsetLeft || 0

    const maxLeft = Math.max(10, wrap.clientWidth - 190)
    const nextLeft = Math.ceil(inputOffset + paddingLeft + measuredWidth + 12)
    materialSuggestLeft.value = Math.max(10, Math.min(maxLeft, nextLeft))
  }

  const onDraftMaterialPick = (item) => {
    setDraftMaterial(item.id)
  }

  const onDraftMaterialFocus = () => {
    materialSuggestOpen.value = false
  }

  const onDraftMaterialBlur = () => {
    window.setTimeout(() => {
      materialSuggestOpen.value = false
    }, 100)
  }

  const onDraftMaterialInput = (value) => {
    const current = getMaterial(draftRow.value.material_id)
    const currentLabel = current ? `${current.name} ${current.spec || ''}`.trim() : ''
    if ((value || '').trim() !== currentLabel) {
      draftRow.value.material_id = null
    }
    updateMaterialSuggestLeft()
    materialSuggestOpen.value = !!`${value || ''}`.trim() && draftMaterialSuggestions.value.length > 0
  }

  const resolveDraftMaterialId = () => {
    if (Number(draftRow.value.material_id)) return Number(draftRow.value.material_id)
    const kw = (draftMaterialText.value || '').trim().toLowerCase()
    if (!kw) return 0
    const matched = materials.value.find((m) => `${m.name} ${m.spec || ''}`.trim().toLowerCase().includes(kw))
    if (!matched) return 0
    draftRow.value.material_id = matched.id
    draftMaterialText.value = `${matched.name} ${matched.spec || ''}`.trim()
    return matched.id
  }

  const prevPage = () => {
    if (page.value <= 1) return
    page.value -= 1
  }

  const nextPage = () => {
    if (page.value >= totalPages.value) return
    page.value += 1
  }

  const openAddDialog = () => {
    editingRowIndex.value = -1
    draftRow.value = createEmptyRow()
    draftMaterialText.value = ''
    addDialogOpen.value = true
  }

  const onRowClick = (row, column) => {
    if (!column || column.type === 'selection') return
    if (selectedRows.value.includes(row)) return
    const idx = rows.value.findIndex((item) => item === row)
    if (idx < 0) return
    editingRowIndex.value = idx
    draftRow.value = {
      date: row.date || today(),
      material_id: Number(row.material_id) || null,
      qty:
        row.qty === '' || row.qty === null || typeof row.qty === 'undefined'
          ? null
          : Number.isFinite(Number(row.qty))
            ? Number(normalizeQty(row.qty))
            : null,
      remark: row.remark || ''
    }
    draftMaterialText.value = `${getMaterial(row.material_id)?.name || ''} ${getMaterial(row.material_id)?.spec || ''}`.trim()
    addDialogOpen.value = true
  }

  const confirmAddRow = () => {
    const isEditing = editingRowIndex.value >= 0
    const materialId = resolveDraftMaterialId()
    if (!draftRow.value.date || !materialId) {
      ElMessage.error('请完整填写日期和名称')
      return
    }
    let qtyValue = ''
    if (draftRow.value.qty !== null && draftRow.value.qty !== '' && typeof draftRow.value.qty !== 'undefined') {
      const parsed = Number(draftRow.value.qty)
      if (Number.isNaN(parsed)) {
        ElMessage.error('数量需为数字')
        return
      }
      qtyValue = normalizeQty(parsed)
    }
    const nextRow = {
      date: draftRow.value.date,
      material_id: materialId,
      qty: qtyValue,
      remark: draftRow.value.remark || ''
    }
    if (editingRowIndex.value >= 0) {
      rows.value.splice(editingRowIndex.value, 1, nextRow)
    } else {
      rows.value.push(nextRow)
    }
    if (!isEditing) {
      page.value = totalPages.value
    }
    selectedRows.value = []
    ElMessage.success(isEditing ? '保存成功' : '添加成功')
    editingRowIndex.value = -1
    draftRow.value = createEmptyRow()
    draftMaterialText.value = ''
    markDraftDirty()
  }

  const onSelectionChange = (selection) => {
    selectedRows.value = selection
  }

  const deleteSelectedRows = () => {
    if (!selectedRows.value.length) return
    rows.value = rows.value.filter((row) => !selectedRows.value.includes(row))
    selectedRows.value = []
    if (page.value > totalPages.value) {
      page.value = totalPages.value
    }
    markDraftDirty()
  }

  const toDraftPayload = () => {
    return rows.value.map((row) => ({
      date: row.date || '',
      material_id: Number(row.material_id) || 0,
      qty: row.qty === '' || row.qty === null || typeof row.qty === 'undefined' ? '' : Number(row.qty),
      remark: row.remark || ''
    }))
  }

  const markDraftDirty = () => {
    draftDirty.value = true
    scheduleDraftSave()
  }

  const saveDraftNow = async (force = false) => {
    const payload = toDraftPayload()
    const serialized = JSON.stringify(payload)
    if (!force && !draftDirty.value && serialized === lastSavedDraftPayload.value) {
      return
    }
    draftSaving.value = true
    try {
      const endpoint = isOut ? '/stock-drafts/out' : '/stock-drafts/in'
      const { data } = await api.put(endpoint, payload)
      draftSavedAt.value = data?.updated_at ? new Date(data.updated_at).toLocaleTimeString() : ''
      draftDirty.value = false
      lastSavedDraftPayload.value = serialized
    } catch (e) {
      ElMessage.error(e.response?.data?.detail || '草稿保存失败')
    } finally {
      draftSaving.value = false
    }
  }

  const scheduleDraftSave = () => {
    if (draftSaveTimer) {
      window.clearTimeout(draftSaveTimer)
    }
    draftSaveTimer = window.setTimeout(() => {
      saveDraftNow()
    }, 500)
  }

  const commitDraft = async () => {
    if (!rows.value.length || commitLoading.value) return
    commitLoading.value = true
    try {
      if (draftSaveTimer) {
        window.clearTimeout(draftSaveTimer)
        draftSaveTimer = null
      }
      await saveDraftNow(true)
      const endpoint = isOut ? '/stock-drafts/out/commit' : '/stock-drafts/in/commit'
      const { data } = await api.post(endpoint)
      ElMessage.success(`入账成功：${data?.result?.order_no || ''}`.trim())
      rows.value = []
      selectedRows.value = []
      page.value = 1
      draftDirty.value = true
      await saveDraftNow(true)
    } catch (e) {
      ElMessage.error(e.response?.data?.detail || '确认入账失败')
    } finally {
      commitLoading.value = false
    }
  }

  const applyQuickDraft = () => {
    const draftRaw = sessionStorage.getItem(QUICK_STOCK_DRAFT_KEY)
    if (!draftRaw) return false
    try {
      const draft = JSON.parse(draftRaw)
      if (draft.type !== mode) return false
      const matched = materials.value.find((m) => m.id === Number(draft.material_id))
      if (!matched) return false
      rows.value = [
        {
          date: today(),
          material_id: matched.id,
          qty: normalizeQty(draft.qty || 1),
          remark: ''
        }
      ]
      return true
    } finally {
      sessionStorage.removeItem(QUICK_STOCK_DRAFT_KEY)
    }
  }

  const loadBase = async () => {
    const draftType = isOut ? 'out' : 'in'
    const [materialsResp, draftResp] = await Promise.all([api.get('/materials'), api.get(`/stock-drafts/${draftType}`)])
    materials.value = materialsResp.data
    const items = Array.isArray(draftResp.data?.items) ? draftResp.data.items : []
    rows.value = items
      .map((row) => ({
        date: `${row?.date || ''}`.trim() || today(),
        material_id: Number(row?.material_id) || null,
        qty:
          row?.qty === '' || row?.qty === null || typeof row?.qty === 'undefined'
            ? ''
            : normalizeQty(row.qty),
        remark: `${row?.remark || ''}`
      }))
      .filter((row) => row.material_id)
    draftSavedAt.value = draftResp.data?.updated_at ? new Date(draftResp.data.updated_at).toLocaleTimeString() : ''
    lastSavedDraftPayload.value = JSON.stringify(toDraftPayload())
    draftDirty.value = false
  }

  const resetPage = async () => {
    page.value = 1
    await loadBase()
    if (applyQuickDraft()) {
      markDraftDirty()
    }
  }

  const onResetEvent = () => {
    resetPage()
  }

  const onCloseAllDialogs = () => {
    addDialogOpen.value = false
  }

  const onBeforeUnload = (event) => {
    if (!rows.value.length) return
    event.preventDefault()
    event.returnValue = ''
  }

  onMounted(async () => {
    window.addEventListener('reset-current-page', onResetEvent)
    window.addEventListener('close-all-dialogs', onCloseAllDialogs)
    window.addEventListener('beforeunload', onBeforeUnload)
    await resetPage()
    if (rows.value.length) {
      ElMessage.warning(`你有 ${rows.value.length} 条${isOut ? '出库' : '入库'}草稿待入账`)
    }
  })

  onBeforeUnmount(() => {
    if (draftSaveTimer) {
      window.clearTimeout(draftSaveTimer)
    }
    window.removeEventListener('beforeunload', onBeforeUnload)
    window.removeEventListener('close-all-dialogs', onCloseAllDialogs)
    window.removeEventListener('reset-current-page', onResetEvent)
  })

  onBeforeRouteLeave(async (_, __, next) => {
    if (draftDirty.value) {
      await saveDraftNow(true)
    }
    if (!rows.value.length) {
      next()
      return
    }
    const ok = window.confirm(`当前有未入账的${isOut ? '出库' : '入库'}草稿，确定离开吗？`)
    next(ok)
  })

  return {
    isManageRoute,
    modeOptions,
    activeMode,
    onModeChange,
    materials,
    page,
    totalPages,
    prevPage,
    nextPage,
    keyword,
    rows,
    pagedRows,
    selectedRows,
    onSelectionChange,
    onRowClick,
    formatIndex,
    getMaterial,
    addDialogOpen,
    openAddDialog,
    editingRowIndex,
    draftDateInput,
    draftRow,
    draftMaterialText,
    materialFieldRef,
    materialSuggestOpen,
    draftMaterialSuggestions,
    materialSuggestLeft,
    onDraftMaterialInput,
    onDraftMaterialFocus,
    onDraftMaterialBlur,
    onDraftMaterialPick,
    setDraftMaterial,
    confirmAddRow,
    deleteSelectedRows,
    draftStatusText,
    commitLoading,
    commitDraft
  }
}
