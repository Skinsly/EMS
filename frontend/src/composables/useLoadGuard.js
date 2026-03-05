import { computed, ref } from 'vue'

export const useLoadGuard = () => {
  const pendingCount = ref(0)

  const run = async (loader, onError) => {
    pendingCount.value += 1
    try {
      return await loader()
    } catch (error) {
      if (typeof onError === 'function') {
        onError(error)
      }
      return null
    } finally {
      pendingCount.value = Math.max(0, pendingCount.value - 1)
    }
  }

  return {
    loading: computed(() => pendingCount.value > 0),
    run
  }
}
