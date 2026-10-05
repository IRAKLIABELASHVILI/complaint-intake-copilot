import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { ApiProvider } from './api/ApiProvider'
import { createApiClient } from './api/client'
import { createQueryClient } from './api/queryClient'
import { App } from './App'
import { AuthProvider } from './auth/AuthProvider'
import { readToken } from './auth/session'
import './index.css'

const root = document.getElementById('root')
if (root === null) throw new Error('index.html has no #root element')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <ApiProvider client={createApiClient(readToken)}>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </ApiProvider>
    </QueryClientProvider>
  </StrictMode>,
)
