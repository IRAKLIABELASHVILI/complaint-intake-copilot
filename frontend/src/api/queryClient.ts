/** The app's query cache settings, shared by the app and its tests. */
import { QueryCache, QueryClient } from '@tanstack/react-query'

import { SESSION_EXPIRED_EVENT } from '../auth/authContext'
import { ApiError } from './client'

export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        // Any 401 means the token is no longer valid: sign out everywhere.
        if (error instanceof ApiError && error.status === 401) {
          window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
        }
      },
    }),
    defaultOptions: {
      queries: {
        // 4xx answers will not change on retry (not found, not allowed); 5xx and network might.
        retry: (failures, error) =>
          !(error instanceof ApiError && error.status < 500) && failures < 2,
      },
    },
  })
}
