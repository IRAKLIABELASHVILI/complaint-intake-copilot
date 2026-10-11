/** The team lead dashboard (US-5) against a fake API: what is shown, and where each number leads. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { User } from '../api/types'
import { saveToken } from '../auth/session'
import { HANDLER, TEAM_LEAD, caseDetail, caseList, dashboard, summaryOf } from '../test/data'
import { HttpStatus, fakeApi } from '../test/fakeApi'
import { renderApp } from '../test/renderApp'

function backend(user: User = TEAM_LEAD) {
  return fakeApi({
    'GET /me': () => user,
    'GET /dashboard': () =>
      user.role === 'team_lead'
        ? dashboard()
        : new HttpStatus(403, { detail: 'Only team leads can see the dashboard' }),
    'GET /cases': () => caseList([summaryOf(caseDetail())]),
  })
}

function signedIn(path: string, user: User = TEAM_LEAD) {
  saveToken('token')
  const api = backend(user)
  const view = renderApp(path, api.fetch)
  return { api, view }
}

describe('the dashboard', () => {
  it('shows deadline risk, with each number linked to its cases', async () => {
    signedIn('/dashboard')

    const deadlines = within(await screen.findByRole('region', { name: 'Deadlines' }))
    const srcOverdue = deadlines.getByRole('link', { name: '3 cases: Summary resolution overdue' })
    expect(srcOverdue).toHaveClass('count-danger')
    expect(srcOverdue).toHaveAttribute(
      'href',
      '/cases?open=true&deadline=src&deadline_risk=overdue',
    )
    expect(deadlines.getByRole('link', { name: '2 cases: Summary resolution at risk' })).toHaveClass(
      'count-warning',
    )
    expect(deadlines.getByText('≤ 2 business days')).toBeInTheDocument()
  })

  it('does not link a zero: there is nothing to open', async () => {
    signedIn('/dashboard')

    const deadlines = within(await screen.findByRole('region', { name: 'Deadlines' }))
    const row = deadlines.getByRole('rowheader', { name: /Final response/ }).closest('tr')
    const cells = within(row as HTMLElement)
    expect(cells.getByText('0')).not.toHaveAttribute('href')
    expect(cells.getAllByRole('link')).toHaveLength(1) // only the overdue one
  })

  it('shows AI suggestions apart from decided categories', async () => {
    signedIn('/dashboard')

    const categories = within(await screen.findByRole('region', { name: 'Open cases by category' }))
    const decided = categories.getByRole('link', { name: '1 case: Fees and charges, decided' })
    const suggested = categories.getByRole('link', {
      name: '4 cases: Fees and charges, suggested by AI',
    })
    expect(decided).toHaveAttribute('href', '/cases?open=true&final_category=fees_and_charges')
    expect(suggested).toHaveAttribute('href', '/cases?open=true&suggested_category=fees_and_charges')
    expect(suggested).toHaveClass('count-suggested')
    expect(categories.getByRole('link', { name: '2 cases: no category yet' })).toHaveAttribute(
      'href',
      '/cases?open=true&uncategorised=true',
    )
  })

  it('counts confirmed vulnerability per indicator, with its FCA driver', async () => {
    signedIn('/dashboard')

    const panel = within(await screen.findByRole('region', { name: 'Confirmed vulnerability' }))
    const row = within(panel.getByRole('rowheader', { name: 'Bereavement' }).closest('tr') as HTMLElement)
    expect(row.getByText('Life events')).toBeInTheDocument()
    expect(row.getByRole('link', { name: '1 case: confirmed bereavement' })).toHaveAttribute(
      'href',
      '/cases?open=true&vulnerability=bereavement',
    )
  })

  it('opens the matching cases and asks the API for exactly those', async () => {
    const { api } = signedIn('/dashboard')

    await userEvent.click(
      await screen.findByRole('link', { name: '3 cases: Summary resolution overdue' }),
    )

    expect(await screen.findByRole('heading', { name: 'Cases' })).toBeInTheDocument()
    const filters = within(screen.getByRole('region', { name: 'Active filters' }))
    expect(filters.getByText('Open cases only')).toBeInTheDocument()
    expect(filters.getByText('Summary resolution deadline: overdue')).toBeInTheDocument()
    await waitFor(() => {
      const list = api.requests.find((request) => request.path === '/cases')
      expect(list?.search.get('open')).toBe('true')
      expect(list?.search.get('deadline')).toBe('src')
      expect(list?.search.get('deadline_risk')).toBe('overdue')
    })
  })

  it('says why when the API cannot count without guessing', async () => {
    saveToken('token')
    const detail = 'Bank holiday data does not cover the coming days. Refresh it.'
    renderApp(
      '/dashboard',
      fakeApi({
        'GET /me': () => TEAM_LEAD,
        'GET /dashboard': () => new HttpStatus(503, { detail }),
      }).fetch,
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
  })

  it('is in the menu for team leads only', async () => {
    signedIn('/cases')
    expect(await screen.findByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
  })
})

describe('a handler', () => {
  it('has no dashboard in the menu', async () => {
    signedIn('/cases', HANDLER)

    await screen.findByRole('heading', { name: 'Cases' })
    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument()
  })

  it('is told the dashboard is for team leads, and the API is not even asked', async () => {
    const { api } = signedIn('/dashboard', HANDLER)

    expect(await screen.findByText('The dashboard is for team leads.')).toBeInTheDocument()
    expect(api.requests.some((request) => request.path === '/dashboard')).toBe(false)
  })
})

describe('the filtered case list', () => {
  it('keeps the dashboard filters when the status changes, and clears them on request', async () => {
    const { api } = signedIn('/cases?open=true&vulnerability=bereavement')

    await screen.findByRole('region', { name: 'Active filters' })
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'in_progress')

    await waitFor(() => {
      const last = api.requests.filter((request) => request.path === '/cases').at(-1)
      expect(last?.search.get('status')).toBe('in_progress')
      expect(last?.search.get('vulnerability')).toBe('bereavement')
    })

    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))

    expect(screen.queryByRole('region', { name: 'Active filters' })).not.toBeInTheDocument()
    await waitFor(() => {
      const last = api.requests.filter((request) => request.path === '/cases').at(-1)
      expect(last?.search.get('status')).toBe('in_progress') // the drop-down's own filter stays
      expect(last?.search.get('vulnerability')).toBeNull()
    })
  })

  it('offers a team lead the way back to the dashboard', async () => {
    signedIn('/cases?open=true&uncategorised=true')

    const filters = within(await screen.findByRole('region', { name: 'Active filters' }))
    expect(filters.getByRole('link', { name: 'Back to the dashboard' })).toHaveAttribute(
      'href',
      '/dashboard',
    )
  })
})
