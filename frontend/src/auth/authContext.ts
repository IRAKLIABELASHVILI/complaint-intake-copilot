import { createContext, useContext } from 'react'

import type { User } from '../api/types'

/** Dispatched on `window` whenever the API answers 401: the user is signed out everywhere. */
export const SESSION_EXPIRED_EVENT = 'cic:session-expired'

export type AuthState =
  | { status: 'checking' }
  | { status: 'signed-out' }
  | { status: 'signed-in'; user: User }

export interface Auth {
  state: AuthState
  signIn: (token: string) => Promise<void>
  signOut: () => void
}

export const AuthContext = createContext<Auth | null>(null)

export function useAuth(): Auth {
  const auth = useContext(AuthContext)
  if (auth === null) throw new Error('useAuth must be used inside <AuthProvider>')
  return auth
}

/** The signed-in user. Only for components rendered behind <RequireAuth>. */
export function useCurrentUser(): User {
  const { state } = useAuth()
  if (state.status !== 'signed-in') throw new Error('useCurrentUser needs a signed-in user')
  return state.user
}
