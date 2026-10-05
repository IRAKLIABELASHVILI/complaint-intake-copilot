/** The app end to end against a fake API: what a handler sees and what is sent to the server. */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { CaseDetail } from './api/types'
import { saveToken } from './auth/session'
import { HANDLER, INDICATOR, caseDetail, caseList, summaryOf } from './test/data'
import { HttpStatus, fakeApi } from './test/fakeApi'
import { renderApp } from './test/renderApp'

const GOOD_TOKEN = 'good-token'

function backend(detail: CaseDetail = caseDetail()) {
  let current = detail
  return fakeApi({
    'GET /me': (request) =>
      request.headers.get('Authorization') === `Bearer ${GOOD_TOKEN}`
        ? HANDLER
        : new HttpStatus(401, { detail: 'Invalid token' }),
    'GET /cases': () => caseList([summaryOf(current, 2)]),
    'GET /cases/:id': ({ url }) =>
      url.endsWith(current.id) ? current : new HttpStatus(404, { detail: 'Case not found' }),
    'GET /cases/:id/audit': () => [],
    'PUT /cases/:id/category': (_request, _params, body) => {
      const { category } = body as { category: CaseDetail['final_category'] }
      current = { ...current, final_category: category, status: 'in_progress' }
      return current
    },
    'PUT /cases/:id/vulnerability-indicators/:indicator/decision': () => {
      current = {
        ...current,
        vulnerability_indicators: [{ ...INDICATOR, decision: 'rejected', decided_by_user_id: HANDLER.id }],
      }
      return current
    },
  })
}

describe('signing in', () => {
  it('sends a visitor to sign in first', async () => {
    renderApp('/cases', backend().fetch)

    expect(await screen.findByLabelText('API token')).toBeInTheDocument()
  })

  it('refuses a wrong token', async () => {
    renderApp('/sign-in', backend().fetch)

    await userEvent.type(await screen.findByLabelText('API token'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('That token was not accepted.')
    expect(sessionStorage.length).toBe(0) // a refused token is not kept
  })

  it('signs in and shows the queue', async () => {
    renderApp('/sign-in', backend().fetch)

    await userEvent.type(await screen.findByLabelText('API token'), GOOD_TOKEN)
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: 'Cases' })).toBeInTheDocument()
    expect(screen.getByText('Nina Handler · Handler')).toBeInTheDocument()
  })

  it('signs out everywhere when the API says the token is no longer valid', async () => {
    saveToken(GOOD_TOKEN)
    const api = backend()
    const routes = api.fetch
    let expired = false
    renderApp('/cases', async (request) =>
      expired && !request.url.endsWith('/me')
        ? new Response(JSON.stringify({ detail: 'Invalid token' }), { status: 401 })
        : routes(request),
    )
    await screen.findByRole('heading', { name: 'Cases' })

    const link = await screen.findByRole('link', { name: 'CMP-2026-AAAA1111' })
    expired = true
    await userEvent.click(link)

    expect(await screen.findByLabelText('API token')).toBeInTheDocument()
    expect(sessionStorage.length).toBe(0)
  })
})

describe('the queue', () => {
  it('shows deadlines and vulnerability flags per case', async () => {
    saveToken(GOOD_TOKEN)
    renderApp('/cases', backend().fetch)

    const row = (await screen.findByRole('link', { name: 'CMP-2026-AAAA1111' })).closest('tr')
    expect(row).not.toBeNull()
    const cells = within(row as HTMLElement)
    expect(cells.getByText('1 business day left')).toHaveClass('deadline-due-soon')
    expect(cells.getByText('38 business days left')).toHaveClass('deadline-ok')
    expect(cells.getByText('2 flags')).toBeInTheDocument()
  })

  it('passes the status filter from the URL to the API', async () => {
    saveToken(GOOD_TOKEN)
    const api = backend()
    renderApp('/cases?status=needs_human_review', api.fetch)

    await screen.findByRole('heading', { name: 'Cases' })
    await waitFor(() => {
      const list = api.requests.find((r) => r.path === '/cases')
      expect(list?.search.get('status')).toBe('needs_human_review')
    })
  })
})

describe('a case', () => {
  it('accepting a suggestion sends exactly that value', async () => {
    saveToken(GOOD_TOKEN)
    const api = backend()
    renderApp('/cases/c-1', api.fetch)

    const category = await screen.findByRole('group', { name: 'Category' })
    await userEvent.click(within(category).getByRole('button', { name: 'Accept suggestion' }))

    await waitFor(() => expect(within(category).getByText('Fees and charges', { selector: 'strong' })).toBeInTheDocument())
    const sent = api.requests.find((r) => r.method === 'PUT')
    expect(sent).toMatchObject({ path: '/cases/c-1/category', body: { category: 'fees_and_charges' } })
  })

  it('rejecting an indicator keeps it visible as rejected', async () => {
    saveToken(GOOD_TOKEN)
    const api = backend()
    renderApp('/cases/c-1', api.fetch)

    await userEvent.click(await screen.findByRole('button', { name: 'Reject' }))

    expect(await screen.findByText('Rejected')).toBeInTheDocument()
    expect(screen.getByText('My husband passed away last month.')).toBeInTheDocument()
    const sent = api.requests.find((r) => r.method === 'PUT')
    expect(sent).toMatchObject({
      path: '/cases/c-1/vulnerability-indicators/i-1/decision',
      body: { decision: 'rejected' },
    })
  })

  it('shows complaint and AI text as plain text, never as HTML', async () => {
    saveToken(GOOD_TOKEN)
    const attack = '<img src=x onerror="window.hacked=true">'
    renderApp(
      '/cases/c-1',
      backend(
        caseDetail({
          body: `Hello ${attack}`,
          vulnerability_indicators: [{ ...INDICATOR, evidence_quote: attack }],
          suggestion: { ...caseDetail().suggestion!, summary: attack },
        }),
      ).fetch,
    )

    expect(await screen.findByText(`Hello ${attack}`)).toBeInTheDocument()
    expect(screen.getAllByText(attack)).toHaveLength(2) // summary and evidence, as text
    expect(document.querySelector('img')).toBeNull()
  })

  it('while analysing: a notice, and nothing to decide yet', async () => {
    saveToken(GOOD_TOKEN)
    renderApp(
      '/cases/c-1',
      backend(caseDetail({ status: 'analysing', suggestion: null, vulnerability_indicators: [] }))
        .fetch,
    )

    expect(await screen.findByText(/The AI analysis is running/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Accept suggestion' })).toBeNull()
  })

  it('needing a person: the reason is shown', async () => {
    saveToken(GOOD_TOKEN)
    renderApp(
      '/cases/c-1',
      backend(
        caseDetail({
          status: 'needs_human_review',
          suggestion: null,
          review_reason: "The model's answer failed validation twice",
        }),
      ).fetch,
    )

    expect(await screen.findByText(/failed validation twice/)).toBeInTheDocument()
  })

  it('an unknown case says so', async () => {
    saveToken(GOOD_TOKEN)
    renderApp('/cases/nope', backend().fetch)

    expect(await screen.findByRole('alert')).toHaveTextContent('Case not found')
  })
})
