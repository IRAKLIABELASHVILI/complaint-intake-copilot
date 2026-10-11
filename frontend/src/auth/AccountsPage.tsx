import { type FormEvent, useState } from 'react'

import { useCreateAccount, useResetPassword, useUsers } from '../api/hooks'
import type { User } from '../api/types'
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
  const [resetting, setResetting] = useState<string | null>(null)
  const [resetDone, setResetDone] = useState('')

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
          setCreated(
            `Account created for ${account.email}. Share the temporary password securely: they choose their own at first sign-in.`,
          )
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
                    <th scope="col">
                      <span className="visually-hidden">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {users.data.map((person) => (
                    <AccountRow
                      key={person.id}
                      person={person}
                      isMe={person.id === user.id}
                      resetting={resetting === person.id}
                      onReset={() => {
                        setResetDone('')
                        setResetting(person.id)
                      }}
                      onDone={(message) => {
                        setResetting(null)
                        setResetDone(message)
                      }}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {resetDone && (
            <p className="notice" role="status">
              {resetDone}
            </p>
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
            <p className="hint">
              At least 12 characters. Temporary: they choose their own at first sign-in.
            </p>
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

interface AccountRowProps {
  person: User
  isMe: boolean
  resetting: boolean
  onReset: () => void
  onDone: (message: string) => void
}

/** A colleague, with "Reset password" opening a small form under their row. */
function AccountRow({ person, isMe, resetting, onReset, onDone }: AccountRowProps) {
  return (
    <>
      <tr>
        <th scope="row">
          {person.display_name}
          {isMe && <span className="muted"> (you)</span>}
        </th>
        <td>{person.email}</td>
        <td>
          {ROLE_LABELS[person.role]}
          {person.is_admin && <span className="badge">Administrator</span>}
          {person.must_change_password && (
            <span className="badge deadline-due-soon">Temporary password</span>
          )}
        </td>
        <td className="number">
          {/* Your own password: Change password, which asks for the current one. */}
          {!isMe && !resetting && (
            <button type="button" className="link-button" onClick={onReset}>
              Reset password
            </button>
          )}
        </td>
      </tr>
      {resetting && (
        <tr>
          <td colSpan={4}>
            <ResetPasswordForm person={person} onDone={onDone} />
          </td>
        </tr>
      )}
    </>
  )
}

/** 16 random characters: strong, and easy enough to read out or paste into a message. */
function randomTemporaryPassword(): string {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (byte) => alphabet[byte % alphabet.length]).join('')
}

function ResetPasswordForm({
  person,
  onDone,
}: {
  person: User
  onDone: (message: string) => void
}) {
  const reset = useResetPassword()
  const [password, setPassword] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    reset.mutate(
      { userId: person.id, password },
      {
        onSuccess: () =>
          onDone(
            `Temporary password set for ${person.display_name}. They were signed out and choose their own at the next sign-in.`,
          ),
      },
    )
  }

  return (
    <form className="reset-password" onSubmit={submit}>
      <label htmlFor={`reset-${person.id}`}>
        Temporary password for {person.display_name}
        <span className="reset-password-input">
          <input
            id={`reset-${person.id}`}
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={12}
            maxLength={256}
          />
          <button type="button" onClick={() => setPassword(randomTemporaryPassword())}>
            Generate
          </button>
        </span>
      </label>
      <p className="hint">
        Shown here so you can pass it on securely. Signing in with it leads straight to choosing
        their own password.
      </p>
      {reset.isError && <ErrorMessage error={reset.error} />}
      <div className="inline">
        <button type="submit" disabled={reset.isPending || password.length < 12}>
          {reset.isPending ? 'Saving…' : 'Set temporary password'}
        </button>
        <button type="button" onClick={() => onDone('')}>
          Cancel
        </button>
      </div>
    </form>
  )
}
