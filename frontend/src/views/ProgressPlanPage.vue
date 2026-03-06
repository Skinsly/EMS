<template>
  <div class="page-card module-page progress-manage-page">
    <div class="stock-page-head">
      <div class="stock-head-actions">
      </div>
      <div class="stock-page-title">进度计划</div>
      <div class="top-pager" aria-hidden="true"></div>
    </div>

    <div v-loading="planLoading" class="gantt-panel">
      <div class="gantt-title">{{ ganttTitle }}</div>
      <div class="gantt-scroll">
        <div class="gantt-canvas" ref="ganttCanvasRef" :style="{ width: `${canvasWidth}px` }">
          <div class="ym-row">
            <div class="index-head-cell">#</div>
            <div
              v-for="segment in ymSegments"
              :key="segment.key"
              class="ym-cell"
              :style="{ left: `${segment.left + indexColWidth}px`, width: `${segment.width}px` }"
            >
              {{ segment.label }}
            </div>
          </div>
          <div class="day-row">
            <div class="index-head-cell">序号</div>
            <div v-for="d in days" :key="d.key" class="day-cell" :style="{ width: `${dayWidth}px` }">
              {{ d.label }}
            </div>
          </div>

          <div class="rows-wrap">
            <div
              v-for="(row, idx) in ganttRows"
              :key="row.id || row._tmpKey || `tmp-${idx}`"
              class="gantt-row"
              :style="{ width: `${canvasWidth}px`, height: `${rowHeight}px` }"
            >
              <div class="row-index">{{ idx + 1 }}</div>
              <div class="row-grid" :style="{ width: `${timelineWidth}px`, '--day-cell-width': `${dayWidth}px` }" @dblclick="onRowDblClick($event, idx)"></div>
              <div
                v-if="!row._placeholder && barGeometry(row)"
                class="bar"
                :class="[barClass(row.status), { 'bar-selected': selectedRow === row }]"
                :style="barGeometry(row)"
                @pointerdown="onBarPointerDown($event, row, 'move')"
                @click.stop="selectBar(row)"
                @dblclick.stop="openEditDialog(row)"
                tabindex="0"
                :aria-label="`任务 ${row.task_name || '未命名任务'}`"
              >
                <div class="bar-handle left" @pointerdown.stop="onBarPointerDown($event, row, 'resize-start')"></div>
                <div class="bar-progress" :style="{ width: `${Math.max(0, Math.min(100, Number(row.progress) || 0))}%` }"></div>
                <span class="bar-text">{{ row.task_name || '未命名任务' }} {{ Number(row.progress) || 0 }}%</span>
                <div class="bar-handle right" @pointerdown.stop="onBarPointerDown($event, row, 'resize-end')"></div>
              </div>
            </div>
          </div>

          <div class="day-row day-row-bottom">
            <div class="index-head-cell">日期</div>
            <div v-for="d in days" :key="`b-${d.key}`" class="day-cell" :style="{ width: `${dayWidth}px` }">
              {{ d.label }}
            </div>
          </div>

          <div
            v-if="dragHint.visible"
            class="drag-hint"
            :style="{ left: `${dragHint.x}px`, top: `${dragHint.y}px` }"
          >
            {{ dragHint.text }}
          </div>

        </div>
      </div>
    </div>

    <el-dialog v-model="taskDialogOpen" width="560px" class="macos-dialog" :fullscreen="taskDialogFullscreen" :show-close="false" @keydown.enter.prevent="saveTaskDialog">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="taskDialogOpen = false" />
            </el-tooltip>
            <el-tooltip :content="taskDialogFullscreen ? '退出最大化' : '最大化'" placement="bottom">
              <button class="mac-window-btn max" type="button" aria-label="最大化" @click="taskDialogFullscreen = !taskDialogFullscreen" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">{{ dialogMode === 'edit' ? '编辑任务' : '新建任务' }}</div>
        </div>
      </template>
      <el-form label-width="0" @keydown.enter.prevent="saveTaskDialog">
        <el-form-item>
          <el-input v-model="taskForm.task_name" placeholder="请输入任务名称" />
        </el-form-item>
        <div class="date-duration-row">
          <el-form-item class="date-field">
            <el-input v-model="taskStartDateInput" placeholder="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item class="duration-field">
            <el-input-number v-model="taskForm.duration_days" :min="1" :step="1" :controls="false" style="width: 120px" />
          </el-form-item>
        </div>
        <el-form-item>
          <el-input v-model="taskForm.note" type="textarea" :rows="3" placeholder="请输入备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="dialogMode === 'edit'" type="danger" @click="deleteTaskFromDialog">删除</el-button>
        <el-button @click="taskDialogOpen = false">取消</el-button>
        <el-button class="dialog-save-plus-btn" type="primary" aria-label="保存" @click="saveTaskDialog">
          <el-icon><Plus /></el-icon>
        </el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../api'
import { formatDateInput, parseDateYmdLocal } from '../utils/date'
import { useLoadGuard } from '../composables/useLoadGuard'
import { useRequestLatest } from '../composables/useRequestLatest'
import { useAuthStore } from '../store'

const auth = useAuthStore()
const { projectName } = storeToRefs(auth)
const rows = ref([])
const ganttCanvasRef = ref(null)
const dayWidth = ref(32)
const indexColWidth = 64
const rowHeight = 42
const dragState = ref(null)
const dragHint = ref({ visible: false, text: '', x: 0, y: 0 })
const selectedRow = ref(null)
const pendingInsertIndex = ref(null)
const taskDialogOpen = ref(false)
const taskDialogFullscreen = ref(false)
const dialogMode = ref('create')
const editingRow = ref(null)
const rowCount = ref(11)
const dayCount = ref(37)
const { loading: planLoading, run: runLoad } = useLoadGuard()
const planRequest = useRequestLatest()
const ganttTitle = computed(() => projectName.value || '工程')
const taskForm = reactive({
  task_name: '',
  owner: '',
  start_date: '',
  duration_days: 1,
  progress: 0,
  status: '未开始',
  predecessor: '',
  note: ''
})

const taskStartDateInput = computed({
  get: () => taskForm.start_date,
  set: (value) => {
    taskForm.start_date = formatDateInput(value)
  }
})

const createEmptyTask = () => ({
  id: null,
  task_name: '',
  owner: '',
  start_date: '',
  duration_days: 30,
  end_date: '',
  progress: 0,
  status: '未开始',
  predecessor: '',
  note: '',
  sort_order: 0
})

const fillTaskForm = (row) => {
  taskForm.task_name = row.task_name || ''
  taskForm.owner = row.owner || ''
  taskForm.start_date = row.start_date || ''
  taskForm.duration_days = Math.max(1, Number(row.duration_days) || 1)
  taskForm.progress = Number(row.progress) || 0
  taskForm.status = row.status || '未开始'
  taskForm.predecessor = row.predecessor || ''
  taskForm.note = row.note || ''
}

const applyTaskFormToRow = (row) => {
  row.task_name = taskForm.task_name
  row.owner = taskForm.owner
  row.start_date = taskForm.start_date
  row.duration_days = Math.max(1, Number(taskForm.duration_days) || 1)
  row.progress = Number(taskForm.progress) || 0
  row.status = taskForm.status || '未开始'
  row.predecessor = taskForm.predecessor
  row.note = taskForm.note
  syncRowDates(row)
}

const syncRowDates = (row) => {
  row.duration_days = Math.max(1, Number(row.duration_days) || 1)
  const s = parseDate(row.start_date)
  if (!s) {
    row.end_date = ''
    return
  }
  row.end_date = formatDate(addDays(s, row.duration_days - 1))
}

const normalizeRow = (row) => {
  const s = parseDate(row.start_date)
  const e = parseDate(row.end_date)
  if (s && e && e >= s) {
    row.duration_days = diffDays(e, s) + 1
  } else {
    row.duration_days = Math.max(1, Number(row.duration_days) || 1)
  }
  syncRowDates(row)
  return row
}

const openEditDialog = (row) => {
  if (!row) return
  selectedRow.value = row
  dialogMode.value = 'edit'
  editingRow.value = row
  fillTaskForm(row)
  taskDialogOpen.value = true
}

const saveTaskDialog = async () => {
  if (dialogMode.value === 'create') {
    const newRow = createEmptyTask()
    applyTaskFormToRow(newRow)
    try {
      const insertAt = pendingInsertIndex.value == null
        ? rows.value.length
        : clamp(pendingInsertIndex.value, 0, rows.value.length)
      const payload = {
        task_name: newRow.task_name,
        owner: newRow.owner,
        start_date: newRow.start_date,
        end_date: newRow.end_date,
        progress: newRow.progress,
        status: newRow.status,
        predecessor: newRow.predecessor,
        note: newRow.note,
        sort_order: insertAt + 1
      }
      const { data } = await api.post('/progress-plans', payload)
      newRow.id = data.id
      rows.value.splice(insertAt, 0, newRow)
      pendingInsertIndex.value = null
      selectedRow.value = newRow
      taskDialogOpen.value = false
      ElMessage.success('任务已保存')
      return
    } catch (e) {
      ElMessage.error(e.response?.data?.detail || '保存失败')
      return
    }
  }
  if (!editingRow.value) return
  pendingInsertIndex.value = null
  applyTaskFormToRow(editingRow.value)
  try {
    const row = editingRow.value
    if (!row.id) return
    const payload = {
      task_name: row.task_name,
      owner: row.owner,
      start_date: row.start_date,
      end_date: row.end_date,
      progress: row.progress,
      status: row.status,
      predecessor: row.predecessor,
      note: row.note,
      sort_order: Math.max(1, rows.value.indexOf(row) + 1)
    }
    await api.put(`/progress-plans/${row.id}`, payload)
    selectedRow.value = row
    taskDialogOpen.value = false
    ElMessage.success('任务已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

const deleteTaskFromDialog = async () => {
  if (!editingRow.value) return
  try {
    await ElMessageBox.confirm('确认删除该任务吗？', '提示', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })

    const target = editingRow.value
    if (target.id) {
      await api.delete(`/progress-plans/${target.id}`)
    }

    const idx = rows.value.indexOf(target)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
    }
    if (selectedRow.value === target) {
      selectedRow.value = null
    }
    editingRow.value = null
    taskDialogOpen.value = false
    ElMessage.success('任务已删除')
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const selectBar = (row) => {
  selectedRow.value = row
}

const persistRow = async (row) => {
  if (!row || !row.id || row._placeholder) return
  syncRowDates(row)
  const payload = {
    task_name: row.task_name,
    owner: row.owner,
    start_date: row.start_date,
    end_date: row.end_date,
    progress: row.progress,
    status: row.status,
    predecessor: row.predecessor,
    note: row.note,
    sort_order: Math.max(1, rows.value.indexOf(row) + 1)
  }
  await api.put(`/progress-plans/${row.id}`, payload)
}

const persistSortOrders = async () => {
  for (let i = 0; i < rows.value.length; i += 1) {
    const row = rows.value[i]
    if (!row?.id || row._placeholder) continue
    syncRowDates(row)
    await api.put(`/progress-plans/${row.id}`, {
      task_name: row.task_name,
      owner: row.owner,
      start_date: row.start_date,
      end_date: row.end_date,
      progress: row.progress,
      status: row.status,
      predecessor: row.predecessor,
      note: row.note,
      sort_order: i + 1
    })
  }
}

const moveSelectedHorizontally = async (deltaDays) => {
  const row = selectedRow.value
  if (!row) return
  const s = parseDate(row.start_date)
  if (!s) return
  row.start_date = formatDate(addDays(s, deltaDays))
  syncRowDates(row)
  try {
    await persistRow(row)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '自动保存失败')
  }
}

const moveSelectedVertically = async (deltaRows) => {
  const row = selectedRow.value
  if (!row) return
  const from = rows.value.indexOf(row)
  if (from < 0) return
  const to = clamp(from + deltaRows, 0, rows.value.length - 1)
  if (to === from) return
  rows.value.splice(from, 1)
  rows.value.splice(to, 0, row)
  try {
    await persistSortOrders()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '自动保存失败')
  }
}

const onGlobalKeydown = (evt) => {
  if (!selectedRow.value || taskDialogOpen.value) return
  const target = evt.target
  if (
    target &&
    (target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.tagName === 'SELECT' ||
      target.isContentEditable)
  ) {
    return
  }
  if (evt.key === 'ArrowLeft') {
    evt.preventDefault()
    moveSelectedHorizontally(-1)
    return
  }
  if (evt.key === 'ArrowRight') {
    evt.preventDefault()
    moveSelectedHorizontally(1)
    return
  }
  if (evt.key === 'ArrowUp') {
    evt.preventDefault()
    moveSelectedVertically(-1)
    return
  }
  if (evt.key === 'ArrowDown') {
    evt.preventDefault()
    moveSelectedVertically(1)
    return
  }
  if (evt.key === 'Delete') {
    evt.preventDefault()
    deleteSelectedByKeyboard()
  }
}

const deleteSelectedByKeyboard = async () => {
  const row = selectedRow.value
  if (!row || row._placeholder) return
  try {
    if (row.id) {
      await api.delete(`/progress-plans/${row.id}`)
    }
    const idx = rows.value.indexOf(row)
    if (idx >= 0) rows.value.splice(idx, 1)
    selectedRow.value = null
    ElMessage.success('任务已删除')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const startOfDay = (date) => {
  const d = new Date(date)
  d.setHours(0, 0, 0, 0)
  return d
}

const parseDate = (str) => {
  if (!str) return null
  const d = parseDateYmdLocal(str)
  if (!d || Number.isNaN(d.getTime())) return null
  return startOfDay(d)
}

const addDays = (date, n) => {
  const d = new Date(date)
  d.setDate(d.getDate() + n)
  return d
}

const diffDays = (a, b) => Math.round((startOfDay(a) - startOfDay(b)) / 86400000)

const timelineRange = computed(() => {
  const today = startOfDay(new Date())
  return {
    start: today,
    end: addDays(today, Math.max(1, Number(dayCount.value) || 1) - 1)
  }
})

const days = computed(() => {
  const arr = []
  const start = timelineRange.value.start
  const end = timelineRange.value.end
  const total = diffDays(end, start) + 1
  for (let i = 0; i < total; i += 1) {
    const d = addDays(start, i)
    arr.push({
      key: d.toISOString(),
      date: d,
      label: String(d.getDate()).padStart(2, '0')
    })
  }
  return arr
})

const timelineWidth = computed(() => Math.max(980, days.value.length * dayWidth.value))
const canvasWidth = computed(() => indexColWidth + timelineWidth.value)

const ymSegments = computed(() => {
  if (!days.value.length) return []
  const segs = []
  let currentMonth = `${days.value[0].date.getFullYear()}-${days.value[0].date.getMonth() + 1}`
  let startIdx = 0

  const pushSegment = (endIdx) => {
    const d = days.value[startIdx].date
    segs.push({
      key: `${d.getFullYear()}-${d.getMonth() + 1}`,
      label: `${d.getFullYear()}.${d.getMonth() + 1}`,
      left: startIdx * dayWidth.value,
      width: (endIdx - startIdx + 1) * dayWidth.value
    })
  }

  for (let i = 1; i < days.value.length; i += 1) {
    const m = `${days.value[i].date.getFullYear()}-${days.value[i].date.getMonth() + 1}`
    if (m !== currentMonth) {
      pushSegment(i - 1)
      currentMonth = m
      startIdx = i
    }
  }
  pushSegment(days.value.length - 1)
  return segs
})

const ganttRows = computed(() => {
  const arr = rows.value.slice()
  const missing = Math.max(0, Math.max(1, Number(rowCount.value) || 1) - arr.length)
  for (let i = 0; i < missing; i += 1) {
    arr.push({ _placeholder: true, _tmpKey: `placeholder-${i}` })
  }
  return arr
})

const barGeometry = (row) => {
  if (row?._placeholder) return null
  const s = parseDate(row.start_date)
  const e = parseDate(row.end_date)
  if (!s || !e || e < s) return null
  const left = diffDays(s, timelineRange.value.start) * dayWidth.value + indexColWidth + 1
  const width = (diffDays(e, s) + 1) * dayWidth.value - 2
  return {
    left: `${left}px`,
    width: `${Math.max(14, width)}px`
  }
}

const barClass = (status) => {
  if (status === '已完成') return 'bar-done'
  if (status === '进行中') return 'bar-doing'
  return 'bar-pending'
}

const onRowDblClick = (evt, rowIndex) => {
  const rect = evt.currentTarget.getBoundingClientRect()
  const x = evt.clientX - rect.left
  const daysFromStart = clamp(Math.floor(x / dayWidth.value), 0, days.value.length - 1)
  const start = addDays(timelineRange.value.start, daysFromStart)
  pendingInsertIndex.value = clamp(Number(rowIndex) || 0, 0, rows.value.length)
  dialogMode.value = 'create'
  editingRow.value = null
  const newTask = createEmptyTask()
  newTask.start_date = formatDate(start)
  fillTaskForm(newTask)
  taskDialogOpen.value = true
}

const formatDate = (d) => {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

const updateDragHint = (evt, row) => {
  const s = parseDate(row.start_date)
  const e = parseDate(row.end_date)
  if (!s || !e || !ganttCanvasRef.value) {
    dragHint.value = { visible: false, text: '', x: 0, y: 0 }
    return
  }
  const rect = ganttCanvasRef.value.getBoundingClientRect()
  const duration = diffDays(e, s) + 1
  dragHint.value = {
    visible: true,
    text: `${formatDate(s)} ~ ${formatDate(e)} (${duration}天)`,
    x: clamp(evt.clientX - rect.left + 12, 8, Math.max(8, rect.width - 220)),
    y: clamp(evt.clientY - rect.top - 28, 8, Math.max(8, rect.height - 40))
  }
}

const onBarPointerDown = (evt, row, mode) => {
  const s = parseDate(row.start_date)
  const e = parseDate(row.end_date)
  if (!s || !e) return
  const currentIndex = rows.value.indexOf(row)
  selectedRow.value = row
  dragState.value = {
    mode,
    row,
    startX: evt.clientX,
    startY: evt.clientY,
    startIndex: currentIndex,
    startDate: s,
    endDate: e
  }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  updateDragHint(evt, row)
}

const onPointerMove = (evt) => {
  if (!dragState.value) return
  const deltaDays = Math.round((evt.clientX - dragState.value.startX) / dayWidth.value)
  const deltaRows = Math.round((evt.clientY - dragState.value.startY) / rowHeight)
  const { row, mode, startDate, endDate, startIndex } = dragState.value
  if (mode === 'move') {
    row.start_date = formatDate(addDays(startDate, deltaDays))
    syncRowDates(row)
    if (deltaRows !== 0 && startIndex >= 0) {
      const from = rows.value.indexOf(row)
      const to = clamp(startIndex + deltaRows, 0, rows.value.length - 1)
      if (from >= 0 && to !== from) {
        rows.value.splice(from, 1)
        rows.value.splice(to, 0, row)
      }
    }
    updateDragHint(evt, row)
    return
  }
  if (mode === 'resize-start') {
    const newStart = addDays(startDate, deltaDays)
    if (newStart <= endDate) {
      row.start_date = formatDate(newStart)
      row.duration_days = diffDays(endDate, newStart) + 1
      syncRowDates(row)
    }
    updateDragHint(evt, row)
    return
  }
  if (mode === 'resize-end') {
    const newEnd = addDays(endDate, deltaDays)
    if (newEnd >= startDate) {
      row.duration_days = diffDays(newEnd, startDate) + 1
      syncRowDates(row)
    }
    updateDragHint(evt, row)
  }
}

const onPointerUp = () => {
  const movedRow = dragState.value?.row
  const movedMode = dragState.value?.mode
  dragState.value = null
  dragHint.value = { visible: false, text: '', x: 0, y: 0 }
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  if (movedRow && movedRow.id && !movedRow._placeholder) {
    const savePromise = movedMode === 'move' ? persistSortOrders() : persistRow(movedRow)
    savePromise.catch((e) => {
      ElMessage.error(e.response?.data?.detail || '自动保存失败')
    })
  }
}

const load = async () => {
  const token = planRequest.next()
  await runLoad(
    async () => {
      const { data } = await api.get('/progress-plans')
      if (!planRequest.isLatest(token)) return
      rows.value = data.map((row) => normalizeRow(row))
    },
    (e) => {
      if (!planRequest.isLatest(token)) return
      ElMessage.error(e.response?.data?.detail || '加载进度计划失败')
    }
  )
}

const resetPage = async () => {
  await load()
}

const onResetEvent = () => {
  resetPage()
}

const onCloseAllDialogs = () => {
  taskDialogOpen.value = false
}

onMounted(() => {
  load()
  window.addEventListener('reset-current-page', onResetEvent)
  window.addEventListener('close-all-dialogs', onCloseAllDialogs)
  window.addEventListener('keydown', onGlobalKeydown)
})

onBeforeUnmount(() => {
  planRequest.invalidate()
  dragHint.value = { visible: false, text: '', x: 0, y: 0 }
  window.removeEventListener('reset-current-page', onResetEvent)
  window.removeEventListener('close-all-dialogs', onCloseAllDialogs)
  window.removeEventListener('keydown', onGlobalKeydown)
  onPointerUp()
})
</script>

<style scoped>
.gantt-panel {
  margin-top: 2px;
  border: 1px solid var(--divider-strong);
  border-radius: 12px;
  overflow: hidden;
  background: transparent;
}

.gantt-title {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  border-bottom: 1px solid var(--divider-strong);
  background: color-mix(in oklab, var(--surface-3) 78%, transparent);
}

.gantt-scroll {
  overflow-x: auto;
  overflow-y: hidden;
  max-width: 100%;
}

.gantt-scroll::-webkit-scrollbar {
  height: var(--scrollbar-size);
}

.gantt-scroll::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border: 1px solid var(--scrollbar-thumb-border);
  border-radius: 999px;
}

.gantt-scroll::-webkit-scrollbar-track {
  background: var(--scrollbar-track);
  border: 1px solid var(--scrollbar-track-border);
  border-radius: 999px;
}

.gantt-canvas {
  position: relative;
  min-height: 160px;
}

.ym-row {
  position: relative;
  height: 32px;
  border-bottom: 1px solid var(--divider-strong);
  background: color-mix(in oklab, var(--surface-3) 62%, transparent);
}

.index-head-cell {
  position: absolute;
  left: 0;
  top: 0;
  width: 64px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-right: 1px solid var(--divider-strong);
  font-size: 12px;
  color: var(--text);
  background: color-mix(in oklab, var(--surface-3) 62%, transparent);
  z-index: 2;
}

.day-row .index-head-cell {
  height: 34px;
  background: color-mix(in oklab, var(--surface-3) 70%, transparent);
}

.day-row-bottom .index-head-cell {
  border-top: 1px solid var(--divider-strong);
}

.ym-cell {
  position: absolute;
  top: 0;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-right: 1px solid var(--divider-strong);
  font-size: 12px;
  color: var(--text);
}

.day-row {
  display: flex;
  height: 34px;
  border-bottom: 1px solid var(--divider-strong);
  background: color-mix(in oklab, var(--surface-3) 70%, transparent);
  padding-left: 64px;
  position: relative;
}

.day-row-bottom {
  border-top: 1px solid var(--divider-strong);
}

.day-cell {
  height: 34px;
  border-right: 1px solid var(--divider-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text);
}

.rows-wrap {
  position: relative;
}

.gantt-row {
  position: relative;
  border-bottom: 1px solid var(--divider-strong);
  background: transparent;
}

.row-index {
  position: absolute;
  left: 0;
  top: 0;
  width: 64px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text);
  border-right: 1px solid var(--divider-strong);
}

.row-grid {
  position: absolute;
  left: 64px;
  top: 0;
  height: 100%;
  --day-cell-width: 32px;
  background-image: repeating-linear-gradient(
    to right,
    transparent 0,
    transparent calc(var(--day-cell-width) - 1px),
    var(--gantt-grid-strong) calc(var(--day-cell-width) - 1px),
    var(--gantt-grid-strong) var(--day-cell-width)
  );
}

.bar {
  position: absolute;
  top: 8px;
  height: 26px;
  border-radius: 999px;
  overflow: hidden;
  border: 1px solid transparent;
  cursor: grab;
}

.bar-selected {
  box-shadow: 0 0 0 2px color-mix(in oklab, var(--panel-solid) 92%, transparent), 0 0 0 4px color-mix(in oklab, var(--accent) 62%, transparent);
}

.bar:active {
  cursor: grabbing;
}

.bar-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 8px;
  background: var(--gantt-handle);
  cursor: ew-resize;
  z-index: 2;
}

.bar-handle.left {
  left: 0;
}

.bar-handle.right {
  right: 0;
}

.bar-progress {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: var(--gantt-progress-overlay);
}

.bar-text {
  position: absolute;
  left: 10px;
  right: 8px;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  color: var(--gantt-text-on-bar);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bar-doing {
  background: linear-gradient(90deg, var(--status-doing-start), var(--status-doing-end));
  border-color: var(--status-doing-border);
}

.bar-done {
  background: linear-gradient(90deg, var(--status-done-start), var(--status-done-end));
  border-color: var(--status-done-border);
}

.bar-pending {
  background: linear-gradient(90deg, var(--status-pending-start), var(--status-pending-end));
  border-color: var(--status-pending-border);
}

.drag-hint {
  position: absolute;
  z-index: 20;
  pointer-events: none;
  background: var(--gantt-hint-bg);
  color: var(--gantt-text-on-bar);
  font-size: 12px;
  border-radius: 8px;
  padding: 6px 10px;
  white-space: nowrap;
  box-shadow: 0 8px 20px color-mix(in oklab, var(--text) 26%, transparent);
}

.date-duration-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.date-duration-row .date-field {
  flex: 1;
  min-width: 0;
}

.date-duration-row .duration-field {
  flex: 0 0 auto;
}

:deep(.date-duration-row .date-field .el-form-item__content) {
  width: 100%;
}

:deep(.date-duration-row .duration-field .el-form-item__content) {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .gantt-title {
    font-size: 15px;
    height: 38px;
  }

  .gantt-panel {
    border-radius: 10px;
  }

  .gantt-scroll {
    -webkit-overflow-scrolling: touch;
    overscroll-behavior-x: contain;
    padding-bottom: 2px;
  }

  .bar {
    top: 7px;
    height: 28px;
  }

  .bar-handle {
    width: 12px;
  }

  .bar-text {
    left: 12px;
    right: 10px;
    font-size: 11px;
  }

  .date-duration-row {
    flex-direction: row;
    gap: 10px;
    align-items: center;
  }

  .date-duration-row .date-field {
    flex: 1;
    min-width: 0;
  }

  .date-duration-row .duration-field {
    flex: 0 0 auto;
  }
}

</style>
