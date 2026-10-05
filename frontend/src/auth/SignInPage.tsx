import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router'

import { ErrorMessage } from '../shared/Layout'
import { useAuth } from './authContext'

export function SignInPage() {
  const { state, signIn } = useAuth()
  const location = useLocation()
  const [token, setToken] = useState('')
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
      await signIn(token)
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="sign-in">
      <h1>Complaint Intake Copilot</h1>
      <form onSubmit={submit} className="panel">
        <label htmlFor="token">API token</label>
        <input
          id="token"
          type="password"
          autoComplete="off"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          required
        />
        <p className="hint">
          Local demo: use a token from the README, for example <code>demo-nb-handler</code>.
        </p>
        {error !== null && <ErrorMessage error={error} />}
        <button type="submit" disabled={busy || token.trim() === ''}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
