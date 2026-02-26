import api from './api'

function filenameFromDisposition(value, fallback) {
  if (!value) return fallback
  const match = value.match(/filename\*?=(?:UTF-8''|"?)([^";]+)/i)
  if (!match) return fallback
  try {
    return decodeURIComponent(match[1].replace(/"/g, ''))
  } catch {
    return match[1].replace(/"/g, '')
  }
}

export async function downloadByApi(url, fallbackName, params = undefined) {
  const config = { responseType: 'blob' }
  if (params && typeof params === 'object') {
    config.params = params
  }
  const res = await api.get(url, config)
  const blobUrl = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filenameFromDisposition(res.headers['content-disposition'], fallbackName)
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(blobUrl)
}
