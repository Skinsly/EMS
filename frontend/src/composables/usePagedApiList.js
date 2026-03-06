import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useLoadGuard } from './useLoadGuard'
import { useRequestLatest } from './useRequestLatest'

export const usePagedApiList = ({
  pageSize = 10,
  fetchPage,
  errorMessage = '加载列表失败',
  onLoadSuccess
}) => {
  const rows = ref([])
  const total = ref(0)
  const page = ref(1)
  const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
  const { loading, run } = useLoadGuard()
  const request = useRequestLatest()

  const load = async () => {
    const token = request.next()
    await run(
      async () => {
        const response = await fetchPage({ page: page.value, pageSize })
        if (!request.isLatest(token)) return
        const data = response?.data || {}
        rows.value = Array.isArray(data?.items) ? data.items : []
        total.value = Number(data?.total || 0)
        const nextTotalPages = Math.max(1, Number(data?.total_pages || 1))
        if (page.value > nextTotalPages) {
          page.value = nextTotalPages
          await load()
          return
        }
        if (typeof onLoadSuccess === 'function') {
          onLoadSuccess(data)
        }
      },
      (error) => {
        if (!request.isLatest(token)) return
        ElMessage.error(error?.response?.data?.detail || errorMessage)
      }
    )
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

  const resetPage = () => {
    page.value = 1
  }

  return {
    rows,
    total,
    page,
    pageSize,
    totalPages,
    loading,
    load,
    prevPage,
    nextPage,
    resetPage,
    invalidate: request.invalidate
  }
}
