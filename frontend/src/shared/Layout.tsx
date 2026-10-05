import type { ReactNode } from 'react'
import { Link, Outlet } from 'react-router'

import { useAuth, useCurrentUser } from '../auth/authContext'

export function Layout() {
  const user = useCurrentUser()
  const { signOut } = useAuth()
  return (
    <>
      <header className="app-header">
        <Link to="/cases" className="brand">
          Complaint Intake Copilot
        </Link>
        <nav aria-label="Main">
          <Link to="/cases">Cases</Link>
          <Link to="/cases/new">New complaint</Link>
        </nav>
        <div className="who">
          <span>
            {user.display_name} · {user.role === 'team_lead' ? 'Team lead' : 'Handler'}
          </span>
          <button type="button" className="link-button" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
      <footer className="app-footer">All data is fictional. AI suggestions are reviewed by a person.</footer>
    </>
  )
}

export function ErrorMessage({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <p role="alert" className="error">
      {message}
    </p>
  )
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel" aria-label={title}>
      <h2>{title}</h2>
      {children}
    </section>
  )
}
