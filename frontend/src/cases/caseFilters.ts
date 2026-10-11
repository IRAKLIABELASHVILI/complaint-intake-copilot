/**
 * The case list's filters, kept in the URL so a view can be bookmarked, shared, and linked to from
 * the dashboard (US-5.4). The names are the API's query parameters, so the URL and the request
 * say the same thing.
 */
import type { CaseStatus, Category, DeadlineKind, DeadlineRisk, IndicatorType } from '../api/types'
import {
  CATEGORY_LABELS,
  DEADLINE_LABELS,
  DEADLINE_RISK_LABELS,
  INDICATOR_LABELS,
  STATUS_LABELS,
  parseCode,
} from '../shared/labels'

export interface CaseFilters {
  q: string | null
  received_from: string | null
  received_to: string | null
  status: CaseStatus | null
  assigned_to_user_id: string | null
  unassigned: boolean
  open: boolean
  deadline: DeadlineKind | null
  deadline_risk: DeadlineRisk | null
  final_category: Category | null
  suggested_category: Category | null
  uncategorised: boolean
  vulnerability: IndicatorType | null
}

export const NO_FILTERS: CaseFilters = {
  q: null, received_from: null, received_to: null,
  status: null,
  assigned_to_user_id: null,
  unassigned: false,
  open: false,
  deadline: null,
  deadline_risk: null,
  final_category: null,
  suggested_category: null,
  uncategorised: false,
  vulnerability: null,
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function parseUuid(value: string | null): string | null {
  return value !== null && UUID.test(value) ? value : null
}

/** Invalid bookmarks return to the first page instead of sending an invalid API offset. */
export function parseOffset(params: URLSearchParams): number {
  const offset = Number(params.get('offset'))
  return Number.isSafeInteger(offset) && offset >= 0 ? offset : 0
}

function parseDate(value: string | null): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const date = new Date(value)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : null
}

/** Reads the filters from a URL. Unknown values are ignored, never sent to the API. */
export function parseFilters(params: URLSearchParams): CaseFilters {
  const deadline = parseCode(DEADLINE_LABELS, params.get('deadline'))
  const risk = parseCode(DEADLINE_RISK_LABELS, params.get('deadline_risk'))
  const bothDeadlineParts = deadline !== null && risk !== null // the API needs both or neither
  return {
    q: params.get('q')?.trim().slice(0, 200) || null,
    received_from: parseDate(params.get('received_from')),
    received_to: parseDate(params.get('received_to')),
    status: parseCode(STATUS_LABELS, params.get('status')),
    assigned_to_user_id: parseUuid(params.get('assigned_to_user_id')),
    unassigned: params.get('unassigned') === 'true',
    open: params.get('open') === 'true',
    deadline: bothDeadlineParts ? deadline : null,
    deadline_risk: bothDeadlineParts ? risk : null,
    final_category: parseCode(CATEGORY_LABELS, params.get('final_category')),
    suggested_category: parseCode(CATEGORY_LABELS, params.get('suggested_category')),
    uncategorised: params.get('uncategorised') === 'true',
    vulnerability: parseCode(INDICATOR_LABELS, params.get('vulnerability')),
  }
}

/** The query string for some filters and a page: only what differs from "everything". */
export function filtersToSearch(filters: Partial<CaseFilters>, offset = 0): URLSearchParams {
  const search = new URLSearchParams()
  for (const [name, value] of Object.entries({ ...NO_FILTERS, ...filters })) {
    if (value === true) search.set(name, 'true')
    else if (typeof value === 'string') search.set(name, value)
  }
  if (offset > 0) search.set('offset', String(offset))
  return search
}

/** A link to the case list showing exactly these cases. */
export function caseListLink(filters: Partial<CaseFilters>): string {
  return `/cases?${filtersToSearch(filters).toString()}`
}

/** The filters as the API's query: no nulls, no "false". */
export function toApiQuery(filters: CaseFilters) {
  return {
    q: filters.q ?? undefined,
    received_from: filters.received_from ?? undefined,
    received_to: filters.received_to ?? undefined,
    status: filters.status ?? undefined,
    assigned_to_user_id: filters.assigned_to_user_id ?? undefined,
    unassigned: filters.unassigned || undefined,
    open: filters.open || undefined,
    deadline: filters.deadline ?? undefined,
    deadline_risk: filters.deadline_risk ?? undefined,
    final_category: filters.final_category ?? undefined,
    suggested_category: filters.suggested_category ?? undefined,
    uncategorised: filters.uncategorised || undefined,
    vulnerability: filters.vulnerability ?? undefined,
  }
}

/** Plain-English lines for every filter except status, which has its own drop-down. */
export function describeFilters(filters: CaseFilters): string[] {
  const lines: string[] = []
  if (filters.q) lines.push(`Search: ${filters.q}`)
  if (filters.received_from) lines.push(`Received from ${filters.received_from} (UTC)`)
  if (filters.received_to) lines.push(`Received through ${filters.received_to} (UTC)`)
  if (filters.assigned_to_user_id) lines.push('Assigned to selected colleague')
  if (filters.unassigned) lines.push('Unassigned cases')
  if (filters.open) lines.push('Open cases only')
  if (filters.deadline && filters.deadline_risk) {
    const deadline = DEADLINE_LABELS[filters.deadline]
    lines.push(`${deadline} deadline: ${DEADLINE_RISK_LABELS[filters.deadline_risk].toLowerCase()}`)
  }
  if (filters.final_category) {
    lines.push(`Category: ${CATEGORY_LABELS[filters.final_category]}`)
  }
  if (filters.suggested_category) {
    const category = CATEGORY_LABELS[filters.suggested_category]
    lines.push(`Suggested by AI, not decided yet: ${category}`)
  }
  if (filters.uncategorised) lines.push('No category yet')
  if (filters.vulnerability) {
    lines.push(`Confirmed vulnerability: ${INDICATOR_LABELS[filters.vulnerability]}`)
  }
  return lines
}

/** What a case link carries in its history state: the query string of the list it was on. */
export interface FromList {
  listSearch: string
}

/** Where "back" goes from a case: the list it was opened from, or all cases. The state is
 * rebuilt through parseFilters, so only real filters ever get into the link. */
export function backToList(state: unknown): { to: string; label: string } {
  const listSearch = (state as Partial<FromList> | null)?.listSearch
  if (typeof listSearch !== 'string') return { to: '/cases', label: '← All cases' }
  const params = new URLSearchParams(listSearch)
  const offset = parseOffset(params)
  const search = filtersToSearch(parseFilters(params), offset).toString()
  return search
    ? { to: `/cases?${search}`, label: '← Back to the list' }
    : { to: '/cases', label: '← All cases' }
}
