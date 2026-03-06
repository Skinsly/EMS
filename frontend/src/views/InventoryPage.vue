<template>
  <div class="page-card module-page inventory-manage-page">
    <StockHeadBar title="库存台账" :page="page" :total-pages="totalPages" @prev="prevPage" @next="nextPage">
      <template #actions>
        <ToolbarSearchInput v-model="keyword" placeholder="按名称/规格搜索" @enter="load" />
        <ToolbarIconAction tooltip="导出库存" aria-label="导出库存" @click="download">
          <Download />
        </ToolbarIconAction>
      </template>
    </StockHeadBar>
    <el-table v-loading="listLoading" class="uniform-row-table no-row-hover-table" :data="rows" border>
      <el-table-column label="序号" width="70">
        <template #default="scope">
          {{ formatIndex(scope.$index) }}
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="spec" label="规格" min-width="180" />
      <el-table-column prop="qty" label="库存" width="120">
        <template #default="scope">
          {{ formatQty(scope.row.qty) }}
        </template>
      </el-table-column>
      <el-table-column prop="unit" label="单位" width="90" />
      <el-table-column prop="updated_at" label="更新时间" min-width="170">
        <template #default="scope">
          {{ formatUpdatedAt(scope.row.updated_at) }}
        </template>
      </el-table-column>
    </el-table>

  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import api from '../api'
import { downloadByApi } from '../download'
import ToolbarSearchInput from '../components/ToolbarSearchInput.vue'
import ToolbarIconAction from '../components/ToolbarIconAction.vue'
import StockHeadBar from '../components/StockHeadBar.vue'
import { usePagedApiList } from '../composables/usePagedApiList'

const keyword = ref('')
const selectedPageSize = 10
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
  errorMessage: '加载库存台账失败',
  fetchPage: ({ page, pageSize }) => api.get('/inventory', { params: { keyword: keyword.value, page, page_size: pageSize } })
})

const formatIndex = (index) => String((page.value - 1) * selectedPageSize + index + 1).padStart(2, '0')

const download = async () => {
  await downloadByApi('/export/inventory', 'inventory.xls')
}

const resetInventoryPage = async () => {
  resetPage()
  keyword.value = ''
  await load()
}

const formatUpdatedAt = (value) => {
  const text = `${value || ''}`.trim()
  if (!text) return '-'
  const normalized = text.replace('T', ' ')
  const match = normalized.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/)
  if (match) {
    return `${match[1]} ${match[2]}`
  }
  return normalized
}

const formatQty = (value) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return value
  return Number.isInteger(n) ? String(n) : n.toFixed(3).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')
}

const onResetEvent = () => {
  resetInventoryPage()
}

onMounted(() => {
  window.addEventListener('reset-current-page', onResetEvent)
  load()
})

onBeforeUnmount(() => {
  invalidate()
  window.removeEventListener('reset-current-page', onResetEvent)
})
</script>
