/** Renders the real app (routes, auth, query cache) against a fake API, at a given URL. */
import { QueryClientProvider } from '@tanstack/react-query'
import { act, render } from '@testing-library/react'
import { useEffect } from 'react'
import { MemoryRouter, useNavigate, type NavigateFunction } from 'react-router'

import { ApiProvider } from '../api/ApiProvider'
import { createApiClient } from '../api/client'
import { createQueryClient } from '../api/queryClient'
import { App } from '../App'
import { AuthProvider } from '../auth/AuthProvider'
import { readToken } from '../auth/session'

export function renderApp(path: string, fetch: (request: Request) => Promise<Response>) {
  const queryClient = createQueryClient()
  queryClient.setDefaultOptions({ queries: { ...queryClient.getDefaultOptions().queries, retry: false } })
  const api = createApiClient(readToken, fetch, 'http://test.local/api')
  let navigate: NavigateFunction | null = null
  const remember = (fn: NavigateFunction) => {
    navigate = fn
  }

  /** Hands the router's navigate to the test, so it can move around inside the app (no reload).
   * In an effect: rendering itself must not change anything outside the component. */
  function NavigationProbe({ onReady }: { onReady: (fn: NavigateFunction) => void }) {
    const fn = useNavigate()
    useEffect(() => onReady(fn), [fn, onReady])
    return null
  }

  const view = render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={api}>
        <MemoryRouter initialEntries={[path]}>
          <NavigationProbe onReady={remember} />
          <AuthProvider>
            <App />
          </AuthProvider>
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  )

  return {
    ...view,
    /** Move within the app, as a link click or the Back button would. */
    goTo: async (to: string) => {
      if (navigate === null) throw new Error('router not ready')
      const go = navigate
      await act(async () => {
        await go(to)
      })
    },
  }
}
