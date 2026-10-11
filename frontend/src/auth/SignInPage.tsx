import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router'

import { ErrorMessage } from '../shared/Layout'
import { useAuth } from './authContext'

export function SignInPage() {
  const { state, signIn } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  if (state.status === 'signed-in') {
    const from = (location.state as { from?: string } | null)?.from ?? '/cases'
    return <Navigate to={from} replace />
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signIn(email, password)
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

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
          <h2>Every complaint answered on time, by a person.</h2>
          <ul>
            <li>Regulatory deadlines counted in business days, for every case.</li>
            <li>AI suggestions for category, priority and vulnerability: a handler decides.</li>
            <li>Every decision recorded in the case history.</li>
          </ul>
        </div>
        <small>All data is fictional.</small>
      </section>
      <section className="sign-in-form">
        <div>
          <h1>Sign in to your workspace</h1>
          <p className="muted">Sign in with the account your administrator created.</p>
          <form onSubmit={submit}>
            <label htmlFor="email">
              Email
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label htmlFor="password">
              Password
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                maxLength={256}
              />
            </label>
            {error !== null && <ErrorMessage error={error} />}
            <button type="submit" disabled={busy || !email.trim() || !password}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
      </section>
    </main>
  )
}
