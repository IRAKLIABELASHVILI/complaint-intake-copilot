import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { saveToken } from './auth/session'
import { HANDLER, caseDetail, caseList, summaryOf } from './test/data'
import { fakeApi } from './test/fakeApi'
import { renderApp } from './test/renderApp'

function routes() {
  const detail = caseDetail()
  return {
    'GET /me': () => HANDLER,
    'GET /cases': () => caseList([summaryOf(detail)]),
    'GET /cases/:id': () => detail,
    'GET /cases/:id/audit': () => [],
  }
}

describe('workspace tools', () => {
  it('searches and saves the current filters', async () => {
    saveToken('good-token')
    const api = fakeApi({ ...routes(), 'POST /saved-views': () => ({ id: 'view-1' }) })
    renderApp('/cases', api.fetch)
    await userEvent.type(await screen.findByLabelText('Search cases'), 'refund')
    await userEvent.click(screen.getByRole('button', { name: /^Search$/ }))
    await waitFor(() => expect(api.requests.some(r => r.path === '/cases' && r.search.get('q') === 'refund')).toBe(true))
    await userEvent.type(screen.getByLabelText('Save current filters'), 'Refund queue')
    await userEvent.click(screen.getByRole('button', { name: 'Save view' }))
    await waitFor(() => expect(api.requests.find(r => r.method === 'POST')?.body).toMatchObject({ name: 'Refund queue', filters: { q: 'refund' } }))
  })

  it('opens my overdue final responses in one click', async () => {
    saveToken('good-token')
    const api = fakeApi(routes())
    renderApp('/cases', api.fetch)
    await userEvent.click(await screen.findByRole('button', { name: 'My overdue cases' }))
    await waitFor(() => expect(api.requests.some(r => r.search.get('assigned_to_user_id') === HANDLER.id && r.search.get('deadline_risk') === 'overdue' && r.search.get('deadline') === 'final_response')).toBe(true))
  })

  it('adds a comment and clears the form on success', async () => {
    saveToken('good-token')
    const api = fakeApi({ ...routes(), 'POST /cases/:id/comments': () => ({ id: 'comment-1' }) })
    renderApp('/cases/c-1', api.fetch)
    await userEvent.type(await screen.findByLabelText('Internal note'), 'Customer called today')
    await userEvent.click(screen.getByRole('button', { name: 'Add comment' }))
    await waitFor(() => expect(api.requests.find(r => r.path.endsWith('/comments'))?.body).toEqual({ note: 'Customer called today' }))
    await waitFor(() => expect(screen.getByLabelText('Internal note')).toHaveValue(''))
  })

  it('requires review before approving the edited draft', async () => {
    saveToken('good-token')
    const draft = { id: 'draft-1', body: 'Draft response', provider: 'fake', created_at: '2026-10-11T10:00:00Z', approved_at: null, approved_by_user_id: null, version: 1 }
    const api = fakeApi({ ...routes(), 'GET /cases/:id/drafts': () => [draft], 'PUT /cases/:id/drafts/:draft': () => draft })
    renderApp('/cases/c-1', api.fetch)
    const approve = await screen.findByRole('button', { name: 'Approve response' })
    expect(approve).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox', { name: /I have checked/ }))
    await userEvent.type(screen.getByLabelText('Response text'), ' edited')
    expect(approve).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox', { name: /I have checked/ }))
    await userEvent.click(approve)
    await waitFor(() => expect(api.requests.find(r => r.method === 'PUT')?.body).toEqual({ body: 'Draft response edited', version: 1, approve: true }))
  })

  it('shows account creation only to an administrator', async () => {
    saveToken('good-token')
    const api = fakeApi({ ...routes(), 'GET /me': () => ({ ...HANDLER, is_admin: true }), 'POST /users': () => ({ ...HANDLER, email: 'new@example.com' }) })
    renderApp('/accounts', api.fetch)
    await userEvent.type(await screen.findByLabelText('Name'), 'New colleague')
    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
    await userEvent.type(screen.getByLabelText('Initial password'), 'long password 123')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Account created for new@example.com')
    expect(screen.getByLabelText('Initial password')).toHaveValue('')
  })

  it('does not approve a draft until its placeholders are filled in', async () => {
    saveToken('good-token')
    const draft = {
      id: 'draft-1',
      body: 'Dear [NAME_1],\n\n[Handler: add verified findings and next steps.]',
      provider: 'fake',
      created_at: '2026-10-11T10:00:00Z',
      approved_at: null,
      approved_by_user_id: null,
      version: 1,
    }
    const api = fakeApi({ ...routes(), 'GET /cases/:id/drafts': () => [draft] })
    renderApp('/cases/c-1', api.fetch)
    const approve = await screen.findByRole('button', { name: 'Approve response' })
    await userEvent.click(screen.getByRole('checkbox', { name: /I have checked/ }))
    expect(approve).toBeDisabled()
    expect(screen.getByText(/Fill in before approving/)).toHaveTextContent(
      '[NAME_1], [Handler: add verified findings and next steps.]',
    )

    const text = screen.getByLabelText('Response text')
    await userEvent.clear(text)
    await userEvent.type(text, 'Dear Ms Ellison, we have refunded the fee.')
    await userEvent.click(screen.getByRole('checkbox', { name: /I have checked/ }))
    expect(approve).toBeEnabled()
    expect(screen.queryByText(/Fill in before approving/)).not.toBeInTheDocument()
  })

  it('names the people in the audit trail instead of showing their ids', async () => {
    saveToken('good-token')
    const colleague = { ...HANDLER, id: 'u-2', display_name: 'Maya Colleague' }
    const event = {
      id: 'e-1',
      action: 'case_assigned',
      field: 'assigned_to_user_id',
      old_value: null,
      new_value: 'u-2',
      source: 'handler',
      actor_user_id: 'u-2',
      correlation_id: null,
      created_at: '2026-10-11T10:00:00Z',
    }
    const api = fakeApi({
      ...routes(),
      'GET /cases/:id/audit': () => [event],
      'GET /users': () => [HANDLER, colleague],
    })
    renderApp('/cases/c-1', api.fetch)
    expect(await screen.findByText(/Assigned to: — → Maya Colleague/)).toBeInTheDocument()
    expect(screen.queryByText(/u-2/)).not.toBeInTheDocument()
    expect(screen.getByText('Maya Colleague', { selector: '.muted' })).toBeInTheDocument()
  })

  it('does not offer to hand a case to the person who already has it', async () => {
    saveToken('good-token')
    const colleague = { ...HANDLER, id: 'u-2', display_name: 'Maya Colleague' }
    const api = fakeApi({
      ...routes(),
      'GET /cases/:id': () => caseDetail({ assigned_to_user_id: HANDLER.id }),
      'GET /users': () => [HANDLER, colleague],
    })
    renderApp('/cases/c-1', api.fetch)
    const handTo = await screen.findByLabelText('Hand over to (optional)')
    await waitFor(() => expect(handTo).toHaveTextContent('Maya Colleague'))
    expect(handTo).not.toHaveTextContent(HANDLER.display_name)
  })
})
