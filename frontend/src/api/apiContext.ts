/**
 * The API client, shared through React context. Components never create their own client, so
 * tests can hand in one backed by a fake `fetch`. C# comparison: constructor injection.
 */
import { createContext, useContext } from 'react'

import type { ApiClient } from './client'

export const ApiContext = createContext<ApiClient | null>(null)

export function useApi(): ApiClient {
  const client = useContext(ApiContext)
  if (client === null) throw new Error('useApi must be used inside <ApiProvider>')
  return client
}
