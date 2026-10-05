import type { ReactNode } from 'react'

import { ApiContext } from './apiContext'
import type { ApiClient } from './client'

export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>
}
