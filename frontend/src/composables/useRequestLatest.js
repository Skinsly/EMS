import { ref } from 'vue'

export const useRequestLatest = () => {
  const seq = ref(0)

  const next = () => {
    seq.value += 1
    return seq.value
  }

  const isLatest = (token) => token === seq.value

  const invalidate = () => {
    seq.value += 1
  }

  return {
    next,
    isLatest,
    invalidate
  }
}
