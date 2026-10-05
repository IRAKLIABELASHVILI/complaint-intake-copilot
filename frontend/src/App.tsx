import { Navigate, Route, Routes } from 'react-router'

import { RequireAuth } from './auth/RequireAuth'
import { SignInPage } from './auth/SignInPage'
import { CaseDetailPage } from './cases/CaseDetailPage'
import { CaseListPage } from './cases/CaseListPage'
import { NewCasePage } from './cases/NewCasePage'
import { Layout } from './shared/Layout'

export function App() {
  return (
    <Routes>
      <Route path="/sign-in" element={<SignInPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/cases" element={<CaseListPage />} />
        <Route path="/cases/new" element={<NewCasePage />} />
        <Route path="/cases/:caseId" element={<CaseDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/cases" replace />} />
    </Routes>
  )
}
