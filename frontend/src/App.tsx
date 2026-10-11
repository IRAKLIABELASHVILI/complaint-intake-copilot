import { Navigate, Route, Routes } from 'react-router'

import { AccountsPage } from './auth/AccountsPage'
import { ChangePasswordPage } from './auth/ChangePasswordPage'
import { CHANGE_PASSWORD_PATH, RequireAuth } from './auth/RequireAuth'
import { SignInPage } from './auth/SignInPage'
import { CaseDetailPage } from './cases/CaseDetailPage'
import { CaseListPage } from './cases/CaseListPage'
import { NewCasePage } from './cases/NewCasePage'
import { DashboardPage } from './dashboard/DashboardPage'
import { Layout } from './shared/Layout'

export function App() {
  return (
    <Routes>
      <Route path="/sign-in" element={<SignInPage />} />
      <Route
        path={CHANGE_PASSWORD_PATH}
        element={
          <RequireAuth>
            <ChangePasswordPage />
          </RequireAuth>
        }
      />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/accounts" element={<AccountsPage />} />
        <Route path="/cases" element={<CaseListPage />} />
        <Route path="/cases/new" element={<NewCasePage />} />
        <Route path="/cases/:caseId" element={<CaseDetailPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/cases" replace />} />
    </Routes>
  )
}
