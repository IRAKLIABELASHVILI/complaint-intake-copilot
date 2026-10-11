import { describe, expect, it } from 'vitest'

import {
  NO_FILTERS,
  backToList,
  caseListLink,
  describeFilters,
  filtersToSearch,
  parseFilters,
  parseOffset,
  toApiQuery,
} from './caseFilters'

const parse = (query: string) => parseFilters(new URLSearchParams(query))

describe('case filters in the URL', () => {
  it.each(['Infinity', '1.5', '-25', 'NaN', '9007199254740992', 'invalid'])(
    'ignores invalid pagination offset %s in both the queue and the back link',
    (offset) => {
      const listSearch = `status=in_progress&offset=${offset}`
      expect(parseOffset(new URLSearchParams(listSearch))).toBe(0)
      expect(backToList({ listSearch }).to).toBe('/cases?status=in_progress')
    },
  )

  it('keeps a valid pagination offset', () => {
    expect(parseOffset(new URLSearchParams('offset=50'))).toBe(50)
    expect(parseOffset(new URLSearchParams())).toBe(0)
  })

  it('reads every filter the dashboard links with', () => {
    const query =
      'status=in_progress&open=true&deadline=src&deadline_risk=at_risk&final_category=other' +
      '&suggested_category=fraud_and_scams&uncategorised=true&vulnerability=job_loss'

    expect(parse(query)).toEqual({
      ...NO_FILTERS,
      status: 'in_progress',
      open: true,
      deadline: 'src',
      deadline_risk: 'at_risk',
      final_category: 'other',
      suggested_category: 'fraud_and_scams',
      uncategorised: true,
      vulnerability: 'job_loss',
    })
  })

  it('ignores values the API does not know, instead of sending them', () => {
    expect(parse('status=toString&final_category=nope&vulnerability=__proto__&open=yes')).toEqual(
      NO_FILTERS,
    )
  })

  it('drops half a deadline filter: the API needs both parts', () => {
    expect(parse('deadline=src')).toEqual(NO_FILTERS)
    expect(parse('deadline_risk=overdue')).toEqual(NO_FILTERS)
  })

  it('writes only what differs from "everything", and survives a round trip', () => {
    const filters = { ...NO_FILTERS, open: true, deadline: 'final_response', deadline_risk: 'overdue' } as const

    const search = filtersToSearch(filters, 50)

    expect(search.toString()).toBe('open=true&deadline=final_response&deadline_risk=overdue&offset=50')
    expect(parseFilters(search)).toEqual(filters)
  })

  it('builds dashboard links to the case list', () => {
    expect(caseListLink({ open: true, vulnerability: 'bereavement' })).toBe(
      '/cases?open=true&vulnerability=bereavement',
    )
  })

  it('sends no empty or false parameters to the API', () => {
    expect(toApiQuery({ ...NO_FILTERS, open: true })).toEqual({
      status: undefined,
      open: true,
      deadline: undefined,
      deadline_risk: undefined,
      final_category: undefined,
      suggested_category: undefined,
      uncategorised: undefined,
      vulnerability: undefined,
    })
  })

  it('describes the active filters in plain English', () => {
    const filters = parse('open=true&deadline=src&deadline_risk=overdue&suggested_category=other')

    expect(describeFilters(filters)).toEqual([
      'Open cases only',
      'Summary resolution deadline: overdue',
      'Suggested by AI, not decided yet: Other',
    ])
    expect(describeFilters(parse('status=new'))).toEqual([]) // status has its own drop-down
  })

  it('goes back to the list a case was opened from, keeping only real filters', () => {
    expect(backToList({ listSearch: 'vulnerability=bereavement&evil=<script>&offset=25' })).toEqual({
      to: '/cases?vulnerability=bereavement&offset=25',
      label: '← Back to the list',
    })
  })

  it.each([null, undefined, 'text', { listSearch: 5 }, { listSearch: '' }, { listSearch: 'status=toString&offset=-3' }])(
    'goes back to all cases from %j',
    (state) => {
      expect(backToList(state)).toEqual({ to: '/cases', label: '← All cases' })
    },
  )
})
