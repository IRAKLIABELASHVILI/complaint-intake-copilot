import { type FormEvent, useState } from 'react'

import { useCreateAccount, useUsers } from '../api/hooks'
import { ErrorMessage, Panel } from '../shared/Layout'
import { useCurrentUser } from './authContext'

const ROLE_LABELS = { handler: 'Handler', team_lead: 'Team lead' } as const

/** Administrators create the accounts of their organisation. There is no self sign-up. */
export function AccountsPage() {
  const user = useCurrentUser()
  const isAdmin = Boolean(user.is_admin)
  const users = useUsers(isAdmin)
  const create = useCreateAccount()
  const [created, setCreated] = useState('')

  if (!isAdmin) {
    return (
      <>
        <h1>Accounts</h1>
        <p className="notice">Only administrators can manage accounts.</p>
      </>
    )
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setCreated('')
    create.mutate(
      {
        display_name: String(data.get('name')).trim(),
        email: String(data.get('email')).trim(),
        password: String(data.get('password')),
        role: data.get('role') === 'team_lead' ? 'team_lead' : 'handler',
        is_admin: data.get('admin') === 'on',
      },
      {
        onSuccess: (account) => {
          setCreated(`Account created for ${account.email}. Share the initial password securely.`)
          form.reset()
        },
      },
    )
  }

  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Accounts</h1>
          <p className="muted">People who can sign in to your organisation's workspace.</p>
        </div>
      </div>
      <div className="accounts-grid">
        <Panel title="Team accounts">
          {users.isPending && <p>Loading accounts…</p>}
          {users.isError && <ErrorMessage error={users.error} />}
          {users.data && (
            <div className="table-scroll">
              <table className="counts">
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Email</th>
                    <th scope="col">Role</th>
                  </tr>
                </thead>
                <tbody>
                  {users.data.map((person) => (
                    <tr key={person.id}>
                      <th scope="row">
                        {person.display_name}
                        {person.id === user.id && <span className="muted"> (you)</span>}
                      </th>
                      <td>{person.email}</td>
                      <td>
                        {ROLE_LABELS[person.role]}
                        {person.is_admin && <span className="badge">Administrator</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        <Panel title="Create account">
          <form onSubmit={submit}>
            <label>
              Name
              <input name="name" required maxLength={200} autoComplete="off" />
            </label>
            <label>
              Email
              <input name="email" type="email" required autoComplete="off" />
            </label>
            <label>
              Initial password
              <input
                name="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={256}
              />
            </label>
            <p className="hint">At least 12 characters.</p>
            <label>
              Role
              <select name="role">
                <option value="handler">{ROLE_LABELS.handler}</option>
                <option value="team_lead">{ROLE_LABELS.team_lead}</option>
              </select>
            </label>
            <label className="inline">
              <input name="admin" type="checkbox" /> Can manage accounts
            </label>
            <button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Creating…' : 'Create account'}
            </button>
            {created && (
              <p className="notice" role="status">
                {created}
              </p>
            )}
            {create.isError && <ErrorMessage error={create.error} />}
          </form>
        </Panel>
      </div>
    </>
  )
}
