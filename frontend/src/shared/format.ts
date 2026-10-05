/**
 * Dates. The API sends UTC; people read UK time, whatever time zone their computer is in.
 * The regulatory deadlines are UK deadlines, so showing them in another zone would be misleading.
 */
const UK = 'Europe/London'

const dateTime = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK,
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

const dateOnly = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK,
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

export function formatDateTime(iso: string): string {
  return safely(dateTime, iso)
}

export function formatDate(iso: string): string {
  return safely(dateOnly, iso)
}

/** An invalid date makes Intl throw, which would take the whole page down: show a dash instead. */
function safely(format: Intl.DateTimeFormat, iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '—' : format.format(date)
}

export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}
