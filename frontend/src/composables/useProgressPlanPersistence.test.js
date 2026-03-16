import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useProgressPlanPersistence } from './useProgressPlanPersistence'

describe('useProgressPlanPersistence', () => {
  it('creates a task and inserts it at target index', async () => {
    const api = { post: vi.fn().mockResolvedValue({ data: { id: 11 } }) }
    const notify = { success: vi.fn() }
    const rows = ref([{ id: 1 }, { id: 2 }])
    const selectedRow = ref(null)
    const { createTask } = useProgressPlanPersistence({ api, notify, rows, selectedRow })

    const task = {
      task_name: 'A', owner: 'U', start_date: '2026-01-01', end_date: '2026-01-02',
      progress: 10, status: '进行中', predecessor: '', note: ''
    }

    await createTask(task, 1)

    expect(api.post).toHaveBeenCalledWith('/progress-plans', expect.objectContaining({ sort_order: 2 }))
    expect(task.id).toBe(11)
    expect(rows.value[1]).toBe(task)
    expect(selectedRow.value).toBe(task)
    expect(notify.success).toHaveBeenCalledWith('任务已保存')
  })

  it('updates an existing task', async () => {
    const api = { put: vi.fn().mockResolvedValue({}) }
    const notify = { success: vi.fn() }
    const row = { id: 7, task_name: 'A', owner: '', start_date: '2026-01-01', end_date: '2026-01-01', progress: 0, status: '未开始', predecessor: '', note: '' }
    const rows = ref([row])
    const selectedRow = ref(null)
    const { updateTask } = useProgressPlanPersistence({ api, notify, rows, selectedRow })

    await updateTask(row)

    expect(api.put).toHaveBeenCalledWith('/progress-plans/7', expect.objectContaining({ sort_order: 1 }))
    expect(selectedRow.value).toBe(row)
    expect(notify.success).toHaveBeenCalledWith('任务已保存')
  })

  it('removes a task and clears selected row', async () => {
    const api = { delete: vi.fn().mockResolvedValue({}) }
    const notify = { success: vi.fn() }
    const row = { id: 9 }
    const rows = ref([row])
    const selectedRow = ref(row)
    const { removeTask } = useProgressPlanPersistence({ api, notify, rows, selectedRow })

    await removeTask(row)

    expect(api.delete).toHaveBeenCalledWith('/progress-plans/9')
    expect(rows.value).toEqual([])
    expect(selectedRow.value).toBeNull()
    expect(notify.success).toHaveBeenCalledWith('任务已删除')
  })
})
