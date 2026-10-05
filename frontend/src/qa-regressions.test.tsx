/**
 * One test per defect found in manual QA (2026-10-05), so none of them can come back.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { AuditEvent, CaseDetail } from './api/types'
import { saveToken } from './auth/session'
import { HANDLER, caseDetail, caseList, summaryOf } from './test/data'
import { HttpStatus, fakeApi } from './test/fakeApi'
import { renderApp } from './test/renderApp'

const TOKEN = 'good-token'

const CASE_A = caseDetail({ id: 'case-a', reference: 'CMP-2026-AAAA0001', subject: 'Case A' })
const CASE_B = caseDetail({
  id: 'case-b',
  reference: 'CMP-2026-BBBB0002',
  subject: 'Case B',
  suggestion: { ...CASE_A.suggestion!, suggested_category: 'service_quality' },
})

function auditEvent(overrides: Partial<AuditEvent>): AuditEvent {
  return {
    id: crypto.randomUUID(),
    action: 'indicator_decided',
    field: 'vulnerability_indicator',
    old_value: null,
    new_value: null,
    source: 'handler',
    actor_user_id: HANDLER.id,
    correlation_id: null,
    created_at: '2026-10-05T09:00:00Z',
    ...overrides,
  }
}

function backend(options: { audit?: AuditEvent[]; onCreate?: (body: unknown) => unknown } = {}) {
  const cases: Record<string, CaseDetail> = { [CASE_A.id]: CASE_A, [CASE_B.id]: CASE_B }
  return fakeApi({
    'GET /me': (request) =>
      request.headers.get('Authorization') === `Bearer ${TOKEN}`
        ? HANDLER
        : new HttpStatus(401, { detail: 'Invalid token' }),
    'GET /cases': ({ url }) => {
      const offset = Number(new URL(url).searchParams.get('offset') ?? 0)
      const all = Object.values(cases).map((c) => summaryOf(c))
      return { ...caseList(offset === 0 ? all : [], all.length), offset }
    },
    'GET /cases/:id': (_request, { id = '' }) =>
      cases[id] ?? new HttpStatus(404, { detail: 'Case not found' }),
    'GET /cases/:id/audit': () => options.audit ?? [],
    'POST /cases': (_request, _params, body) => options.onCreate?.(body) ?? CASE_A,
  })
}

describe('BUG-1: signing in returns to the exact view asked for', () => {
  it('keeps the filter of a deep link', async () => {
    const api = backend()
    renderApp('/cases?status=in_progress', api.fetch)

    await userEvent.type(await screen.findByLabelText('API token'), TOKEN)
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await screen.findByRole('heading', { name: 'Cases' })
    await waitFor(() => {
      const list = api.requests.find((r) => r.path === '/cases')
      expect(list?.search.get('status')).toBe('in_progress')
    })
  })
})

describe('BUG-2: a page past the end of the list', () => {
  it('says so and leads back to the first page', async () => {
    saveToken(TOKEN)
    renderApp('/cases?offset=25', backend().fetch)

    expect(await screen.findByText(/past the end of the list/)).toBeInTheDocument()
    expect(screen.queryByText('No cases.')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Go to the first page' }))
    expect(await screen.findByRole('link', { name: 'CMP-2026-AAAA0001' })).toBeInTheDocument()
  })
})

describe('OBS-3: the audit trail is in plain words', () => {
  it('names fields and values as people say them', async () => {
    saveToken(TOKEN)
    renderApp(
      '/cases/case-a',
      backend({
        audit: [
          auditEvent({
            old_value: { id: 'i-1', decision: 'pending' },
            new_value: { id: 'i-1', decision: 'rejected' },
          }),
          auditEvent({
            action: 'category_decided',
            field: 'category',
            new_value: 'fees_and_charges',
            source: 'accepted_suggestion',
          }),
          auditEvent({
            action: 'analysis_failed',
            field: 'status',
            old_value: 'analysing',
            new_value: { status: 'needs_human_review', reason: 'Invalid twice' },
            source: 'system',
            actor_user_id: null,
          }),
        ],
      }).fetch,
    )

    const audit = await screen.findByRole('region', { name: 'Audit trail' })
    expect(await within(audit).findByText(/Vulnerability indicator: Pending → Rejected/)).toBeInTheDocument()
    expect(within(audit).getByText(/Category: — → Fees and charges/)).toBeInTheDocument()
    expect(
      within(audit).getByText(/Status: Analysing → Needs human review \(Invalid twice\)/),
    ).toBeInTheDocument()
    expect(audit).not.toHaveTextContent('vulnerability_indicator')
  })
})

describe('BUG-4: moving between cases never carries a half-made choice along', () => {
  it('shows each case its own values, even when the next case is already cached', async () => {
    saveToken(TOKEN)
    const app = renderApp('/cases/case-a', backend().fetch)
    const categoryOf = async () =>
      within(await screen.findByRole('group', { name: 'Category' })).getByRole('combobox')

    expect(await categoryOf()).toHaveValue('fees_and_charges') // case A: its own suggestion
    await app.goTo('/cases/case-b')
    await screen.findByRole('heading', { name: /Case B/ })
    await userEvent.selectOptions(await categoryOf(), 'other') // chosen on B, never saved

    await app.goTo('/cases/case-a') // A is cached: no loading screen in between
    await screen.findByRole('heading', { name: /Case A/ })

    expect(await categoryOf()).toHaveValue('fees_and_charges')
  })
})

describe('BUG-6 and OBS-5: the new complaint form', () => {
  async function fillIn() {
    await userEvent.type(await screen.findByLabelText('Subject'), 'Card blocked')
    await userEvent.type(screen.getByLabelText('Complaint'), 'My card was blocked abroad.')
    await userEvent.type(screen.getByLabelText('Customer email'), 'sam@example.com')
  }

  it('creates one case however many times Create is pressed', async () => {
    saveToken(TOKEN)
    const api = backend()
    renderApp('/cases/new', api.fetch)
    await fillIn()

    const create = screen.getByRole('button', { name: 'Create case' })
    fireEvent.click(create)
    fireEvent.click(create)
    fireEvent.click(create)

    await screen.findByRole('heading', { name: /Case A/ })
    const posts = api.requests.filter((r) => r.method === 'POST')
    expect(posts).toHaveLength(1)
    // And if a retry ever reaches the API, this id makes it return the same case.
    const sent = posts[0]?.body as { external_message_id?: string } | undefined
    expect(sent?.external_message_id).toMatch(/^web-form:[0-9a-f-]{32,36}$/)
  })

  it('reports invalid fields with the labels on the form', async () => {
    saveToken(TOKEN)
    renderApp(
      '/cases/new',
      backend({
        onCreate: () =>
          new HttpStatus(422, {
            detail: [
              { loc: ['body', 'body'], msg: 'String should have at least 1 character' },
              { loc: ['body', 'received_at'], msg: 'Value error, cannot be in the future' },
            ],
          }),
      }).fetch,
    )
    await fillIn()

    await userEvent.click(screen.getByRole('button', { name: 'Create case' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(
      'Complaint: String should have at least 1 character. Received: cannot be in the future',
    )
    expect(alert).not.toHaveTextContent('Value error')
  })
})
