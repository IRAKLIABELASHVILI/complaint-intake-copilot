import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { HANDLER, TEAM_LEAD, caseList } from '../test/data'
import { HttpStatus, fakeApi } from '../test/fakeApi'
import { renderApp } from '../test/renderApp'
import { saveToken } from './session'

const NEW_PASSWORD = 'my own password 456'

describe('a temporary password', () => {
  it('leads straight to choosing a new one, and then to the cases', async () => {
    saveToken('good-token')
    let me = { ...HANDLER, must_change_password: true }
    const api = fakeApi({
      'GET /me': () => me,
      'GET /cases': () => caseList([]),
      'POST /auth/password': () => {
        me = { ...me, must_change_password: false }
        return new HttpStatus(204)
      },
    })
    renderApp('/cases', api.fetch)

    expect(await screen.findByRole('heading', { name: 'Choose your own password' })).toBeVisible()
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument()
    expect(api.requests.some((request) => request.path === '/cases')).toBe(false)

    await userEvent.type(screen.getByLabelText('Temporary password'), 'temporary password 1')
    await userEvent.type(screen.getByLabelText('New password'), NEW_PASSWORD)
    await userEvent.type(screen.getByLabelText('Repeat the new password'), NEW_PASSWORD)
    await userEvent.click(screen.getByRole('button', { name: 'Save and continue' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Cases' })).toBeVisible())
    expect(screen.getByRole('status')).toHaveTextContent('Your password was changed')
    expect(api.requests.find((request) => request.path === '/auth/password')?.body).toEqual({
      current_password: 'temporary password 1',
      new_password: NEW_PASSWORD,
    })
  })

  it('only saves a long enough, repeated, different password', async () => {
    saveToken('good-token')
    const api = fakeApi({ 'GET /me': () => ({ ...HANDLER, must_change_password: true }) })
    renderApp('/change-password', api.fetch)
    const save = await screen.findByRole('button', { name: 'Save and continue' })

    await userEvent.type(screen.getByLabelText('Temporary password'), 'temporary password 1')
    await userEvent.type(screen.getByLabelText('New password'), 'short')
    expect(screen.getByText(/At least 12 characters \(5 so far\)/)).toBeInTheDocument()
    expect(save).toBeDisabled()

    await userEvent.clear(screen.getByLabelText('New password'))
    await userEvent.type(screen.getByLabelText('New password'), NEW_PASSWORD)
    await userEvent.type(screen.getByLabelText('Repeat the new password'), 'something else 12')
    expect(screen.getByText('The two passwords are not the same.')).toBeInTheDocument()
    expect(save).toBeDisabled()

    await userEvent.clear(screen.getByLabelText('New password'))
    await userEvent.type(screen.getByLabelText('New password'), 'temporary password 1')
    expect(screen.getByText('Choose a password different from the current one.')).toBeVisible()
    expect(save).toBeDisabled()
  })

  it('shows the API answer when the temporary password is wrong', async () => {
    saveToken('good-token')
    const api = fakeApi({
      'GET /me': () => ({ ...HANDLER, must_change_password: true }),
      'POST /auth/password': () =>
        new HttpStatus(403, { detail: 'The current password is not correct.' }),
    })
    renderApp('/change-password', api.fetch)
    await userEvent.type(await screen.findByLabelText('Temporary password'), 'wrong one')
    await userEvent.type(screen.getByLabelText('New password'), NEW_PASSWORD)
    await userEvent.type(screen.getByLabelText('Repeat the new password'), NEW_PASSWORD)
    await userEvent.click(screen.getByRole('button', { name: 'Save and continue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The current password is not correct.',
    )
  })
})

describe('changing your own password', () => {
  it('is in the sidebar and can be cancelled', async () => {
    saveToken('good-token')
    const api = fakeApi({ 'GET /me': () => HANDLER, 'GET /cases': () => caseList([]) })
    renderApp('/cases', api.fetch)
    await userEvent.click(await screen.findByRole('link', { name: 'Change password' }))
    expect(await screen.findByRole('heading', { name: 'Change password' })).toBeVisible()
    expect(screen.getByLabelText('Current password')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('link', { name: 'Cancel' }))
    expect(await screen.findByRole('heading', { name: 'Cases' })).toBeVisible()
  })
})

describe('an administrator resetting a password', () => {
  it('sets a generated temporary password for a colleague, never for themselves', async () => {
    saveToken('good-token')
    const admin = { ...TEAM_LEAD, is_admin: true }
    const api = fakeApi({
      'GET /me': () => admin,
      'GET /users': () => [admin, HANDLER],
      'POST /users/:id/password': () => new HttpStatus(204),
    })
    renderApp('/accounts', api.fetch)

    const myRow = (await screen.findByText('(you)')).closest('tr') as HTMLElement
    expect(within(myRow).queryByRole('button', { name: 'Reset password' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Reset password' }))
    const field = screen.getByLabelText(`Temporary password for ${HANDLER.display_name}`)
    await userEvent.click(screen.getByRole('button', { name: 'Generate' }))
    expect((field as HTMLInputElement).value).toMatch(/^[A-Za-z2-9]{16}$/)

    await userEvent.click(screen.getByRole('button', { name: 'Set temporary password' }))
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        `Temporary password set for ${HANDLER.display_name}`,
      ),
    )
    const sent = api.requests.find((request) => request.path.endsWith('/password'))
    expect(sent?.path).toBe(`/users/${HANDLER.id}/password`)
    expect(sent?.body).toEqual({ temporary_password: (field as HTMLInputElement).value })
  })
})
