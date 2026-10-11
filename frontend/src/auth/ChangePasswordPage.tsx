import { type FormEvent, useState } from 'react'
import { Link, Navigate } from 'react-router'

import { useChangePassword } from '../api/hooks'
import { ErrorMessage } from '../shared/Layout'
import { useAuth, useCurrentUser } from './authContext'
import { PASSWORD_MIN_LENGTH as MIN_LENGTH } from './passwordRules'


/**
 * Choose a new password. Forced after an administrator set a temporary one: until then this is
 * the only page, with no navigation. Otherwise it is the user's own choice and can be cancelled.
 */
export function ChangePasswordPage() {
  const user = useCurrentUser()
  const { signOut } = useAuth()
  const change = useChangePassword()
  const forced = user.must_change_password
  const [saved, setSaved] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')

  const tooShort = next.length > 0 && next.length < MIN_LENGTH
  const mismatch = repeat.length > 0 && repeat !== next
  const sameAsCurrent = next.length > 0 && next === current
  const ready = current !== '' && next.length >= MIN_LENGTH && next === repeat && !sameAsCurrent

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!ready) return
    change.mutate(
      { current_password: current, new_password: next },
      { onSuccess: () => setSaved(true) },
    )
  }

  // Leave only once /me no longer asks for a new password; going earlier would send the user
  // straight back here.
  if (saved && !forced) return <Navigate to="/cases" replace state={{ passwordChanged: true }} />

  return (
    <main className="sign-in">
      <section className="sign-in-brand" aria-label="About">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true">
            CI
          </span>
          Complaint Intake Copilot
        </span>
        <div>
          <h2>{forced ? 'One more step before you start.' : 'Keep your account yours.'}</h2>
          <ul>
            <li>Use at least {MIN_LENGTH} characters. A short sentence is easy to remember.</li>
            <li>Do not reuse a password from another service.</li>
            <li>Changing it signs you out on every other device.</li>
          </ul>
        </div>
        <small>All data is fictional.</small>
      </section>
      <section className="sign-in-form">
        <div>
          <h1>{forced ? 'Choose your own password' : 'Change password'}</h1>
          <p className="muted">
            {forced
              ? `Signed in as ${user.email} with a temporary password from your administrator. Replace it to continue.`
              : `Signed in as ${user.email}.`}
          </p>
          <form onSubmit={submit} noValidate>
            <label htmlFor="current-password">
              {forced ? 'Temporary password' : 'Current password'}
              <input
                id="current-password"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
                required
                maxLength={256}
              />
            </label>
            <div className="field">
              <label htmlFor="new-password">New password</label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(event) => setNext(event.target.value)}
                required
                minLength={MIN_LENGTH}
                maxLength={256}
                aria-describedby="new-password-hint"
                aria-invalid={tooShort || sameAsCurrent}
              />
              <span
                id="new-password-hint"
                className={tooShort || sameAsCurrent ? 'field-error' : 'hint'}
              >
                {sameAsCurrent
                  ? 'Choose a password different from the current one.'
                  : `At least ${MIN_LENGTH} characters${next ? ` (${next.length} so far)` : ''}.`}
              </span>
            </div>
            <div className="field">
              <label htmlFor="repeat-password">Repeat the new password</label>
              <input
                id="repeat-password"
                type="password"
                autoComplete="new-password"
                value={repeat}
                onChange={(event) => setRepeat(event.target.value)}
                required
                maxLength={256}
                aria-invalid={mismatch}
              />
              {mismatch && <span className="field-error">The two passwords are not the same.</span>}
            </div>
            {change.isError && <ErrorMessage error={change.error} />}
            <button type="submit" disabled={!ready || change.isPending}>
              {change.isPending ? 'Saving…' : forced ? 'Save and continue' : 'Change password'}
            </button>
          </form>
          <p className="sign-in-secondary">
            {forced ? (
              <button type="button" className="link-button" onClick={signOut}>
                Sign out
              </button>
            ) : (
              <Link to="/cases">Cancel</Link>
            )}
          </p>
        </div>
      </section>
    </main>
  )
}
