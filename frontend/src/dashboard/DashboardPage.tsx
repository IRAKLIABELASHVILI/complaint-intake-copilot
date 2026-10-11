import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { useDashboard } from '../api/hooks'
import type { AssigneeCount, Dashboard, DeadlineKind, DeadlineRisk } from '../api/types'
import { useCurrentUser } from '../auth/authContext'
import { type CaseFilters, caseListLink } from '../cases/caseFilters'
import { formatDateTime, initials, plural } from '../shared/format'
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
        <div>
          <p className="eyebrow">Team overview</p>
          <h1>Dashboard</h1>
          <p className="muted">Ownership, workload and deadlines — in one place.</p>
        </div>
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
        <>
          <KeyMetrics dashboard={dashboard.data} />
          <TeamWorkload dashboard={dashboard.data} />
          <div className="dashboard-grid">
            <div>
              <DeadlinesPanel dashboard={dashboard.data} />
              <VulnerabilityPanel dashboard={dashboard.data} />
            </div>
            <CategoriesPanel dashboard={dashboard.data} />
          </div>
        </>
      )}
    </>
  )
}

function KeyMetrics({ dashboard }: { dashboard: Dashboard }) {
  const unassigned = dashboard.assignments.find((item) => item.user_id === null)?.open_cases ?? 0
  return (
    <section className="overview-metrics" aria-label="Key metrics">
      <article className="metric-card">
        <span>Open workload</span>
        <strong>{dashboard.open_cases}</strong>
        <small>Cases requiring attention</small>
      </article>
      <article className="metric-card metric-warning">
        <span>Awaiting an owner</span>
        <strong>
          <CountLink
            count={unassigned}
            filters={{ unassigned: true }}
            label="unassigned open cases"
          />
        </strong>
        <small>Assign these cases to your team</small>
      </article>
      <article className="metric-card">
        <span>Final response at risk</span>
        <strong>{dashboard.final_response.at_risk}</strong>
        <small>Due within {dashboard.at_risk_business_days} business days</small>
      </article>
      <article className="metric-card metric-danger">
        <span>Overdue final responses</span>
        <strong>{dashboard.final_response.overdue}</strong>
        <small>Prioritise these cases</small>
      </article>
    </section>
  )
}

function TeamWorkload({ dashboard }: { dashboard: Dashboard }) {
  return (
    <Panel title="Team workload">
      <p className="muted">
        Who owns the open cases. Select a colleague to see their assigned cases.
      </p>
      {dashboard.assignments.length === 0 ? (
        <p className="notice">No open cases. Your team is up to date.</p>
      ) : (
        <div className="workload-grid">
          {dashboard.assignments.map((item) => (
            <WorkloadCard
              key={item.user_id ?? 'unassigned'}
              item={item}
              total={dashboard.open_cases}
            />
          ))}
        </div>
      )}
    </Panel>
  )
}

/** One person's open cases (or the unassigned ones), linking to exactly those cases. */
function WorkloadCard({ item, total }: { item: AssigneeCount; total: number }) {
  const owner = item.user_id ? { assigned_to_user_id: item.user_id } : { unassigned: true }
  return (
    <Link
      className={`workload-card${item.user_id ? '' : ' workload-unassigned'}`}
      to={caseListLink({ ...OPEN, ...owner })}
    >
      <span className="owner-avatar" aria-hidden="true">
        {item.user_id ? initials(item.display_name) : '?'}
      </span>
      <span className="workload-person">
        <strong>{item.display_name}</strong>
        <span>{plural(item.open_cases, 'open case')}</span>
        <progress
          value={item.open_cases}
          max={Math.max(total, 1)}
          aria-label={`${item.display_name}: share of open cases`}
        />
      </span>
      <span className="workload-arrow" aria-hidden="true">
        →
      </span>
    </Link>
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
