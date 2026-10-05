/**
 * Who is signed in. The state is derived, never copied: no token means signed out; a token means
 * "whatever GET /me says about it". A token is only kept after the API has accepted it, and any
 * 401 later on (expired or revoked token) signs the user out everywhere.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { useApi } from '../api/apiContext'
import { ApiError, unwrap, type ApiClient } from '../api/client'
import type { User } from '../api/types'
import { AuthContext, SESSION_EXPIRED_EVENT, type AuthState } from './authContext'
import { clearToken, readToken, saveToken } from './session'

const meKey = (token: string | null) => ['me', token] as const

async function fetchMe(api: ApiClient): Promise<User> {
  try {
    return unwrap(await api.GET('/me'))
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) clearToken()
    throw error
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const api = useApi()
  const queryClient = useQueryClient()
  const [token, setToken] = useState(readToken)

  const me = useQuery({
    queryKey: meKey(token),
    queryFn: () => fetchMe(api),
    enabled: token !== null,
    retry: false,
    staleTime: Infinity, // who you are does not change while you are signed in
  })

  const signOut = useCallback(() => {
    clearToken()
    queryClient.clear() // no cached cases from this user may survive
    setToken(null)
  }, [queryClient])

  const signIn = useCallback(
    async (candidate: string) => {
      const trimmed = candidate.trim()
      saveToken(trimmed) // the client reads the token from the session for this request
      try {
        await queryClient.fetchQuery({ queryKey: meKey(trimmed), queryFn: () => fetchMe(api) })
      } catch (error) {
        clearToken()
        if (error instanceof ApiError && error.status === 401) {
          throw new ApiError(401, 'That token was not accepted.')
        }
        throw error
      }
      setToken(trimmed)
    },
    [api, queryClient],
  )

  useEffect(() => {
    window.addEventListener(SESSION_EXPIRED_EVENT, signOut)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, signOut)
  }, [signOut])

  const state: AuthState = useMemo(() => {
    if (token === null || me.isError) return { status: 'signed-out' }
    if (me.data) return { status: 'signed-in', user: me.data }
    return { status: 'checking' }
  }, [token, me.isError, me.data])

  const auth = useMemo(() => ({ state, signIn, signOut }), [state, signIn, signOut])
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
}
