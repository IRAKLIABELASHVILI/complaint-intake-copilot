import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { useAuth } from './authContext'

export const CHANGE_PASSWORD_PATH = '/change-password'

/** Pages behind this need a signed-in user; others are sent to sign in, then back. A user with
 * a temporary password is sent to choose their own first (the API refuses everything else). */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth()
  const location = useLocation()
  if (state.status === 'checking') return <p className="page">Checking your session…</p>
  if (state.status === 'signed-out') {
    // The whole address, filters included, so signing in returns to exactly this view.
    return <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />
  }
  if (state.user.must_change_password && location.pathname !== CHANGE_PASSWORD_PATH) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />
  }
  return children
}
