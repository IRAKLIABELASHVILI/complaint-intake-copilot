import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { useAuth } from './authContext'

/** Pages behind this need a signed-in user; others are sent to sign in, then back. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth()
  const location = useLocation()
  if (state.status === 'checking') return <p className="page">Checking your session…</p>
  if (state.status === 'signed-out') {
    // The whole address, filters included, so signing in returns to exactly this view.
    return <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />
  }
  return children
}
