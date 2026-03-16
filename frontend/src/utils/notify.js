import { ElMessage } from 'element-plus'

const normalize = (options) => (typeof options === 'string' ? { message: options } : options)

export const notify = {
  success(options) {
    return ElMessage.success(normalize(options))
  },
  error(options) {
    return ElMessage.error(normalize(options))
  },
  warning(options) {
    return ElMessage.warning(normalize(options))
  },
  info(options) {
    return ElMessage.info(normalize(options))
  }
}
