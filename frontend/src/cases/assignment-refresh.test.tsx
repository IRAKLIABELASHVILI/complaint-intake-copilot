import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { saveToken } from '../auth/session'
import { caseDetail, caseList, summaryOf, TEAM_LEAD } from '../test/data'
import { fakeApi } from '../test/fakeApi'
import { renderApp } from '../test/renderApp'

describe('changes made by another user', () => {
  it.each(['/cases?status=awaiting_review', '/cases/c-1'])(
    'refreshes assignment and release without navigation on %s',
    async (path) => {
      saveToken('test-token')
      let current = caseDetail()
      const api = fakeApi({
        'GET /me': () => TEAM_LEAD,
        'GET /cases': () => caseList([summaryOf(current)]),
        'GET /cases/:id': () => current,
        'GET /cases/:id/audit': () => [],
      })
      renderApp(path, api.fetch)
      expect(await screen.findByText('Unassigned', { selector: 'span, dd' })).toBeInTheDocument()

      // A different session assigns the case; this browser performs no mutation or navigation.
      current = { ...current, assigned_to_user_id: 'colleague', assigned_to_display_name: 'Maya Colleague' }
      expect(await screen.findByText('Maya Colleague', {}, { timeout: 7000 })).toBeInTheDocument()
      current = { ...current, assigned_to_user_id: null, assigned_to_display_name: null }
      await waitFor(() => expect(screen.getByText('Unassigned', { selector: 'span, dd' })).toBeInTheDocument(), { timeout: 7000 })
      if (path.startsWith('/cases?')) {
        const requests = api.requests.filter((request) => request.path === '/cases')
        expect(requests.length).toBeGreaterThanOrEqual(3)
        expect(requests.every((request) => request.search.get('status') === 'awaiting_review')).toBe(true)
      }
    },
    20000,
  )
})

describe('status changes made by another user', () => {
  it.each(['/cases', '/cases/c-1'])(
    'updates the status badge without navigation on %s',
    async (path) => {
      saveToken('test-token')
      let current = caseDetail()
      const api = fakeApi({
        'GET /me': () => TEAM_LEAD,
        'GET /cases': () => caseList([summaryOf(current)]),
        'GET /cases/:id': () => current,
        'GET /cases/:id/audit': () => [],
      })
      renderApp(path, api.fetch)
      expect(await screen.findByText('Awaiting review', { selector: '.badge' })).toBeInTheDocument()
      current = { ...current, status: 'in_progress' }
      expect(await screen.findByText('In progress', { selector: '.badge' }, { timeout: 7000 })).toBeInTheDocument()
      expect(screen.queryByText('Awaiting review', { selector: '.badge' })).not.toBeInTheDocument()
    },
    12000,
  )

  it('removes a case from Awaiting review and updates the empty state when its status changes', async () => {
    saveToken('test-token')
    let current = caseDetail()
    const api = fakeApi({
      'GET /me': () => TEAM_LEAD,
      'GET /cases': (request) => {
        const status = new URL(request.url).searchParams.get('status')
        return caseList(current.status === status ? [summaryOf(current)] : [])
      },
    })
    renderApp('/cases?status=awaiting_review', api.fetch)
    expect(await screen.findByRole('link', { name: current.reference })).toBeInTheDocument()
    current = { ...current, status: 'in_progress' }
    await waitFor(() => {
      expect(screen.queryByRole('link', { name: current.reference })).not.toBeInTheDocument()
      expect(screen.getByLabelText('Status')).toHaveValue('awaiting_review')
      expect(screen.queryByRole('navigation', { name: 'Pages' })).not.toBeInTheDocument()
    }, { timeout: 7000 })
    expect(screen.getByText(/No cases/)).toBeInTheDocument()
  }, 12000)
})
