export const formatDateInput = (value) => {
  const digits = String(value || '')
    .replace(/\D/g, '')
    .slice(0, 8)
  const yyyy = digits.slice(0, 4)
  const mm = digits.slice(4, 6)
  const dd = digits.slice(6, 8)
  if (!mm) return yyyy
  if (!dd) return `${yyyy}-${mm}`
  return `${yyyy}-${mm}-${dd}`
}

export const parseDateYmdLocal = (value) => {
  const text = String(value || '').trim()
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const date = new Date(year, month - 1, day)
  if (
    date.getFullYear() !== year ||
    date.getMonth() + 1 !== month ||
    date.getDate() !== day
  ) {
    return null
  }
  return date
}
