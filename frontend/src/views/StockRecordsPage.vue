<template>
  <div class="page-card module-page stock-records-page">
    <StockHeadBar title-class="stock-title-segment-wrap" :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage">
      <template #actions>
        <ToolbarSearchInput v-model="keyword" placeholder="按名称/规格搜索" @enter="load" />
        <ToolbarIconAction tooltip="更正选中" aria-label="更正选中" type="danger" :disabled="!selectedRows.length" @click="correctSelected">
          <Edit />
        </ToolbarIconAction>
        <ToolbarIconAction :tooltip="exportLabel" :aria-label="exportLabel" @click="download">
          <Download />
        </ToolbarIconAction>
      </template>
      <template #title>
        <el-segmented v-model="recordType" :options="recordTypeOptions" class="stock-dark-segment" @change="onFilterChange" />
      </template>
    </StockHeadBar>

    <el-table v-loading="listLoading" class="uniform-row-table clickable-table" :data="rows" border @selection-change="onSelectionChange" @row-click="openDetailByRow">
      <el-table-column type="selection" width="50" />
      <el-table-column label="序号" width="70">
        <template #default="scope">
          {{ formatIndex(scope.$index) }}
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="日期" width="150">
        <template #default="scope">
          {{ formatDate(scope.row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="materials_summary" label="名称" min-width="220" />
      <el-table-column prop="specs_summary" label="规格" min-width="160" />
      <el-table-column prop="total_qty" label="数量" width="130">
        <template #default="scope">
          {{ formatQty(scope.row.total_qty) }}
        </template>
      </el-table-column>
      <el-table-column prop="unit" label="单位" width="90" />
      <el-table-column prop="remark" label="备注" min-width="180" />
    </el-table>

    <el-dialog v-model="detailOpen" width="min(520px, 90vw)" class="macos-dialog stock-record-detail-dialog" :show-close="false" :close-on-press-escape="false">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="detailOpen = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">记录详情</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="更正" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="更正" @click="openCorrectDialog(detailRow)">
                <el-icon><Edit /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <el-descriptions :column="1" border class="stock-record-detail-card">
        <el-descriptions-item label="类型">{{ detailRow.type === 'in' ? '入库' : '出库' }}</el-descriptions-item>
        <el-descriptions-item label="单号">{{ detailRow.order_no || '-' }}</el-descriptions-item>
        <el-descriptions-item label="日期">{{ formatDate(detailRow.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="名称">{{ detailRow.materials_summary || '-' }}</el-descriptions-item>
        <el-descriptions-item label="规格">{{ detailRow.specs_summary || '-' }}</el-descriptions-item>
        <el-descriptions-item label="数量">{{ formatQty(detailRow.total_qty) }}</el-descriptions-item>
        <el-descriptions-item label="单位">{{ detailRow.unit || '-' }}</el-descriptions-item>
        <el-descriptions-item label="备注">{{ detailRow.remark || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <el-dialog v-model="correctOpen" width="min(500px, 90vw)" class="macos-dialog stock-record-detail-dialog" :show-close="false" :close-on-press-escape="false">
      <template #header>
        <div class="mac-dialog-header">
          <div class="mac-dialog-controls">
            <el-tooltip content="关闭" placement="bottom">
              <button class="mac-window-btn close" type="button" aria-label="关闭" @click="correctOpen = false" />
            </el-tooltip>
          </div>
          <div class="mac-dialog-title">更正记录</div>
          <div class="dialog-header-actions-left">
            <el-tooltip content="确认" placement="bottom">
              <button class="dialog-save-plus-btn" type="button" aria-label="确认" :disabled="correctSubmitting" @click="submitCorrect">
                <el-icon><Check /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </template>
      <el-alert title="已入账记录将通过冲正单更正，不直接修改原始记录。" type="warning" :closable="false" show-icon />
      <el-form label-width="0" style="margin-top: 12px" @keydown.enter.prevent="submitCorrect">
        <el-form-item>
          <el-input :model-value="`${correctTarget.type === 'in' ? '入库' : '出库'} · ${correctTarget.order_no || ''}`" disabled />
        </el-form-item>
        <el-form-item>
          <el-input v-model="correctReason" placeholder="请填写更正原因" />
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Check, Download, Edit } from '@element-plus/icons-vue'
import api from '../api'
import { downloadByApi } from '../download'
import ToolbarSearchInput from '../components/ToolbarSearchInput.vue'
import ToolbarIconAction from '../components/ToolbarIconAction.vue'
import StockHeadBar from '../components/StockHeadBar.vue'
import { useLoadGuard } from '../composables/useLoadGuard'
import { useRequestLatest } from '../composables/useRequestLatest'
import { notify } from '../utils/notify'

const rows = ref([])
const total = ref(0)
const selectedRows = ref([])
const page = ref(1)
const pageSize = 20
const recordType = ref('in')
const keyword = ref('')
const recordTypeOptions = [
  { label: '入库', value: 'in' },
  { label: '出库', value: 'out' }
]
const exportLabel = computed(() => (recordType.value === 'out' ? '导出出库表' : '导出入库表'))
const detailOpen = ref(false)
const detailRow = reactive({ type: 'in', order_no: '', created_at: '', materials_summary: '', specs_summary: '', total_qty: '', unit: '', remark: '' })
const correctOpen = ref(false)
const correctTarget = reactive({ type: 'in', order_no: '' })
const correctReason = ref('')
const correctSubmitting = ref(false)
const { loading: listLoading, run: runLoad } = useLoadGuard()
const listRequest = useRequestLatest()

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

const formatDate = (value) => {
  const text = `${value || ''}`.trim()
  if (!text) return '-'
  return text.replace('T', ' ').slice(0, 10)
}

const formatQty = (value) => {
  const text = `${value ?? ''}`.trim()
  if (!text) return '0'
  const n = Number(text)
  if (!Number.isFinite(n)) return text
  return Number.isInteger(n) ? String(n) : n.toFixed(3).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')
}

const formatIndex = (indexOnPage) => String((page.value - 1) * pageSize + indexOnPage + 1).padStart(2, '0')

const load = async () => {
  const token = listRequest.next()
  await runLoad(
    async () => {
      const { data } = await api.get('/stock-records', {
        params: {
          record_type: recordType.value,
          keyword: keyword.value,
          page: page.value,
          page_size: pageSize
        }
      })
      if (!listRequest.isLatest(token)) return
      rows.value = data.items || []
      total.value = Number(data.total || 0)
      if (page.value > totalPages.value) {
        page.value = totalPages.value
        await load()
      }
    },
    (e) => {
      if (!listRequest.isLatest(token)) return
      notify.error(e.response?.data?.detail || '加载记录失败')
    }
  )
}

const onFilterChange = async () => {
  page.value = 1
  await load()
}

const prevPage = async () => {
  if (page.value <= 1) return
  page.value -= 1
  await load()
}

const nextPage = async () => {
  if (page.value >= totalPages.value) return
  page.value += 1
  await load()
}

const download = async () => {
  await downloadByApi('/export/stock-records', 'stock-records.xls', {
    record_type: recordType.value,
    keyword: keyword.value
  })
}

const onSelectionChange = (items) => {
  selectedRows.value = items
}

const openDetailByRow = (row) => {
  if (!row) return
  detailRow.type = row.type
  detailRow.order_no = row.order_no
  detailRow.raw_order_no = row.raw_order_no || row.order_no
  detailRow.created_at = row.created_at
  detailRow.materials_summary = row.materials_summary
  detailRow.specs_summary = row.specs_summary
  detailRow.total_qty = row.total_qty
  detailRow.unit = row.unit
  detailRow.remark = row.remark
  detailOpen.value = true
}

const openCorrectDialog = (row) => {
  correctTarget.type = row.type
  correctTarget.order_no = row.raw_order_no || row.order_no
  correctReason.value = ''
  correctOpen.value = true
}

const submitCorrect = async () => {
  if (correctSubmitting.value) return
  if (!correctReason.value.trim()) {
    notify.error('请填写更正原因')
    return
  }
  correctSubmitting.value = true
  try {
    await api.post('/stock-records/correct', {
      record_type: correctTarget.type,
      order_no: correctTarget.order_no,
      reason: correctReason.value
    })
    notify.success('更正成功，已生成冲正单')
    correctOpen.value = false
    detailOpen.value = false
    selectedRows.value = []
    await load()
  } catch (e) {
    notify.error(e.response?.data?.detail || '更正失败')
  } finally {
    correctSubmitting.value = false
  }
}

const correctSelected = () => {
  if (!selectedRows.value.length) return
  if (selectedRows.value.length > 1) {
    notify.error('一次只能更正一条记录')
    return
  }
  openCorrectDialog(selectedRows.value[0])
}

onMounted(() => {
  load()
})

onBeforeUnmount(() => {
  listRequest.invalidate()
})
</script>

<style scoped>
.stock-record-detail-dialog :deep(.el-dialog__body) {
  background: var(--panel-solid);
}

.stock-record-detail-card :deep(.el-descriptions__body),
.stock-record-detail-card :deep(.el-descriptions__cell),
.stock-record-detail-card :deep(.el-descriptions__label) {
  background: var(--panel-solid) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
}

.stock-record-detail-card :deep(.el-descriptions__content) {
  color: var(--text) !important;
}
</style>
