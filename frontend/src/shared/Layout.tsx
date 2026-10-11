import type { ReactNode } from 'react'
import { Link, NavLink, Outlet } from 'react-router'

import { useAuth, useCurrentUser } from '../auth/authContext'
import { initials } from './format'
import { ChartIcon, InboxIcon, PlusIcon, UsersIcon } from './icons'
import { Notifications } from './Notifications'

/** The signed-in app: navigation on the left, deadline alerts above every page. */
export function Layout() {
  const user = useCurrentUser()
  const { signOut } = useAuth()
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/cases" className="brand">
          <span className="brand-mark" aria-hidden="true">
            CI
          </span>
          Complaint Intake Copilot
        </Link>
        <nav aria-label="Main" className="sidebar-nav">
          {/* `end`: "Cases" is not also highlighted on /cases/new. */}
          <NavLink to="/cases" end>
            <InboxIcon />
            Cases
          </NavLink>
          {user.role === 'team_lead' && (
            <NavLink to="/dashboard">
              <ChartIcon />
              Dashboard
            </NavLink>
          )}
          <NavLink to="/cases/new">
            <PlusIcon />
            New complaint
          </NavLink>
          {user.is_admin && (
            <NavLink to="/accounts">
              <UsersIcon />
              Accounts
            </NavLink>
          )}
        </nav>
        <div className="who">
          <span className="avatar" aria-hidden="true">
            {initials(user.display_name)}
          </span>
          <span className="who-text">
            <span>
              {user.display_name} · {user.role === 'team_lead' ? 'Team lead' : 'Handler'}
            </span>
          </span>
          <button type="button" className="link-button" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <Notifications />
        </header>
        <main className="page">
          <Outlet />
        </main>
        <footer className="app-footer">
          All data is fictional. AI suggestions are reviewed by a person.
        </footer>
      </div>
    </div>
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

interface PanelProps {
  title: string
  children: ReactNode
  className?: string
}

export function Panel({ title, children, className }: PanelProps) {
  return (
    <section className={className ? `panel ${className}` : 'panel'} aria-label={title}>
      <h2>{title}</h2>
      {children}
    </section>
  )
}
