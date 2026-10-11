import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { useDashboard } from '../api/hooks'
import type { Dashboard, DeadlineKind, DeadlineRisk } from '../api/types'
import { useCurrentUser } from '../auth/authContext'
import { type CaseFilters, caseListLink } from '../cases/caseFilters'
import { formatDateTime, plural } from '../shared/format'
import {
  CATEGORY_LABELS,
  DEADLINE_LABELS,
  DEADLINE_RISK_LABELS,
  DRIVER_LABELS,
  INDICATOR_LABELS,
} from '../shared/labels'
import { ErrorMessage, Panel } from '../shared/Layout'

/** Every number on the dashboard counts open cases, so every link shows open cases. */
const OPEN = { open: true } as const

/**
 * US-5: the team lead's view of risk. What is close to breach, what is overdue, and where the
 * categories and the vulnerability are. Every number opens the matching cases (US-5.4).
 */
export function DashboardPage() {
  const user = useCurrentUser()
  const isTeamLead = user.role === 'team_lead'
  const dashboard = useDashboard(isTeamLead)

  if (!isTeamLead) {
    return (
      <>
        <h1>Dashboard</h1>
        <p className="notice">The dashboard is for team leads.</p>
      </>
    )
  }
  return (
    <>
      <div className="page-title">
        <h1>Dashboard</h1>
        {dashboard.data && (
          <p className="muted">
            <CountLink count={dashboard.data.open_cases} filters={{}} label="open cases">
              {plural(dashboard.data.open_cases, 'open case')}
            </CountLink>{' '}
            · updated {formatDateTime(dashboard.data.generated_at)}
          </p>
        )}
      </div>
      {dashboard.isPending && <p>Loading the dashboard…</p>}
      {dashboard.isError && <ErrorMessage error={dashboard.error} />}
      {dashboard.data && (
        <div className="dashboard-grid">
          <div>
            <DeadlinesPanel dashboard={dashboard.data} />
            <VulnerabilityPanel dashboard={dashboard.data} />
          </div>
          <CategoriesPanel dashboard={dashboard.data} />
        </div>
      )}
    </>
  )
}

/** A count that opens the matching cases. Zero is not a link: there is nothing to open. */
function CountLink({
  count,
  filters,
  label,
  tone,
  children,
}: {
  count: number
  filters: Partial<CaseFilters>
  label: string
  tone?: 'danger' | 'warning' | 'suggested'
  children?: ReactNode
}) {
  if (count === 0) return <span className="count zero">{children ?? 0}</span>
  return (
    <Link
      to={caseListLink({ ...OPEN, ...filters })}
      className={`count${tone ? ` count-${tone}` : ''}`}
      aria-label={`${plural(count, 'case')}: ${label}`}
    >
      {children ?? count}
    </Link>
  )
}

interface DeadlineRow {
  kind: DeadlineKind
  field: 'summary_resolution' | 'final_response'
  rule: string
}

const DEADLINE_ROWS: DeadlineRow[] = [
  { kind: 'src', field: 'summary_resolution', rule: '3 business days' },
  { kind: 'final_response', field: 'final_response', rule: '8 weeks' },
]
const RISK_TONES: Record<DeadlineRisk, 'warning' | 'danger'> = {
  at_risk: 'warning',
  overdue: 'danger',
}

function DeadlinesPanel({ dashboard }: { dashboard: Dashboard }) {
  const risks: DeadlineRisk[] = ['at_risk', 'overdue']
  return (
    <Panel title="Deadlines">
      <table className="counts">
        <thead>
          <tr>
            <th scope="col">Deadline</th>
            <th scope="col" className="number">
              At risk
              <span className="hint">
                ≤ {plural(dashboard.at_risk_business_days, 'business day')}
              </span>
            </th>
            <th scope="col" className="number">
              Overdue
            </th>
          </tr>
        </thead>
        <tbody>
          {DEADLINE_ROWS.map(({ kind, field, rule }) => (
            <tr key={kind}>
              <th scope="row">
                {DEADLINE_LABELS[kind]}
                <span className="hint">{rule}</span>
              </th>
              {risks.map((risk) => (
                <td key={risk} className="number">
                  <CountLink
                    count={dashboard[field][risk]}
                    filters={{ deadline: kind, deadline_risk: risk }}
                    label={`${DEADLINE_LABELS[kind]} ${DEADLINE_RISK_LABELS[risk].toLowerCase()}`}
                    tone={RISK_TONES[risk]}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">
        Missing the summary resolution deadline is not a breach: the case then needs a final
        response within 8 weeks. An overdue final response is a breach.
      </p>
    </Panel>
  )
}

function CategoriesPanel({ dashboard }: { dashboard: Dashboard }) {
  return (
    <Panel title="Open cases by category">
      <table className="counts">
        <thead>
          <tr>
            <th scope="col">Category</th>
            <th scope="col" className="number">
              Decided
            </th>
            <th scope="col" className="number">
              Suggested by AI
              <span className="hint">not decided yet</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {dashboard.categories.map(({ category, decided, suggested }) => (
            <tr key={category}>
              <th scope="row">{CATEGORY_LABELS[category]}</th>
              <td className="number">
                <CountLink
                  count={decided}
                  filters={{ final_category: category }}
                  label={`${CATEGORY_LABELS[category]}, decided`}
                />
              </td>
              <td className="number">
                <CountLink
                  count={suggested}
                  filters={{ suggested_category: category }}
                  label={`${CATEGORY_LABELS[category]}, suggested by AI`}
                  tone="suggested"
                />
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">
              No category yet
              <span className="hint">being analysed, or the analysis failed</span>
            </th>
            <td className="number" colSpan={2}>
              <CountLink
                count={dashboard.uncategorised}
                filters={{ uncategorised: true }}
                label="no category yet"
              />
            </td>
          </tr>
        </tfoot>
      </table>
    </Panel>
  )
}

function VulnerabilityPanel({ dashboard }: { dashboard: Dashboard }) {
  return (
    <Panel title="Confirmed vulnerability">
      <table className="counts">
        <thead>
          <tr>
            <th scope="col">Indicator</th>
            <th scope="col">Driver</th>
            <th scope="col" className="number">
              Open cases
            </th>
          </tr>
        </thead>
        <tbody>
          {dashboard.vulnerabilities.map(({ indicator_type, driver, cases }) => (
            <tr key={indicator_type}>
              <th scope="row">{INDICATOR_LABELS[indicator_type]}</th>
              <td className="muted">{DRIVER_LABELS[driver]}</td>
              <td className="number">
                <CountLink
                  count={cases}
                  filters={{ vulnerability: indicator_type }}
                  label={`confirmed ${INDICATOR_LABELS[indicator_type].toLowerCase()}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">Only indicators a person confirmed. Pending ones are on each case.</p>
    </Panel>
  )
}
