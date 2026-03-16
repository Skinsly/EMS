export const useProgressPlanPersistence = ({ api, notify, rows, selectedRow }) => {
  const buildPayload = (row, sortOrder) => ({
    task_name: row.task_name,
    owner: row.owner,
    start_date: row.start_date,
    end_date: row.end_date,
    progress: row.progress,
    status: row.status,
    predecessor: row.predecessor,
    note: row.note,
    sort_order: sortOrder
  })

  const persistRow = async (row, syncRowDates) => {
    if (!row || !row.id || row._placeholder) return
    syncRowDates(row)
    await api.put(`/progress-plans/${row.id}`, buildPayload(row, Math.max(1, rows.value.indexOf(row) + 1)))
  }

  const persistSortOrders = async (syncRowDates) => {
    for (let i = 0; i < rows.value.length; i += 1) {
      const row = rows.value[i]
      if (!row?.id || row._placeholder) continue
      syncRowDates(row)
      await api.put(`/progress-plans/${row.id}`, buildPayload(row, i + 1))
    }
  }

  const createTask = async (newRow, insertAt) => {
    const { data } = await api.post('/progress-plans', buildPayload(newRow, insertAt + 1))
    newRow.id = data.id
    rows.value.splice(insertAt, 0, newRow)
    selectedRow.value = newRow
    notify.success('任务已保存')
  }

  const updateTask = async (row) => {
    if (!row?.id) return
    await api.put(`/progress-plans/${row.id}`, buildPayload(row, Math.max(1, rows.value.indexOf(row) + 1)))
    selectedRow.value = row
    notify.success('任务已保存')
  }

  const removeTask = async (row) => {
    if (row?.id) {
      await api.delete(`/progress-plans/${row.id}`)
    }
    const idx = rows.value.indexOf(row)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
    }
    if (selectedRow.value === row) {
      selectedRow.value = null
    }
    notify.success('任务已删除')
  }

  return {
    createTask,
    updateTask,
    removeTask,
    persistRow,
    persistSortOrders
  }
}
