export const DATE_TIME_PICKER_FORMAT = 'YYYY-MM-DD HH:mm:ss'

type DateTimeValue = string | number | Date | null | undefined

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function parseDateTime(value: DateTimeValue) {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value

  if (typeof value === 'number') {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? null : date
  }

  const text = String(value).trim()
  if (!text) return null

  const hasExplicitTimezone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(text)
  if (!hasExplicitTimezone) {
    const localMatch = text.match(
      /^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s](\d{1,2}):(\d{1,2})(?::(\d{1,2})(?:\.\d+)?)?)?$/
    )
    if (localMatch) {
      const [, year, month, day, hour = '0', minute = '0', second = '0'] = localMatch
      const date = new Date(
        Number(year),
        Number(month) - 1,
        Number(day),
        Number(hour),
        Number(minute),
        Number(second)
      )
      return Number.isNaN(date.getTime()) ? null : date
    }
  }

  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value: DateTimeValue, fallback = '-') {
  const date = parseDateTime(value)
  if (!date) return fallback

  return [
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`,
  ].join(' ')
}
