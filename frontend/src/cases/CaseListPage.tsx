import { Link, useSearchParams } from 'react-router'

import { PAGE_SIZE, useCases } from '../api/hooks'
import type { CaseStatus, CaseSummary } from '../api/types'
import { useCurrentUser } from '../auth/authContext'
import { formatDateTime, initials, plural } from '../shared/format'
import { STATUS_LABELS, optionsOf, parseStatus } from '../shared/labels'
import { ErrorMessage } from '../shared/Layout'
import { assigneeLabel } from './assignee'
import {
  type CaseFilters,
  type FromList,
  describeFilters,
  filtersToSearch,
  parseFilters,
  parseOffset,
} from './caseFilters'
import { CaseSearch, SavedViews } from './components/SearchViews'
import { DeadlineBadge, FlagCount, StatusBadge } from './components/badges'

type AssignmentFilters = Pick<CaseFilters, 'assigned_to_user_id' | 'unassigned'>

/** The queue's three views by owner. Switching view keeps every other filter. */
const ASSIGNMENT_VIEWS: { label: string; view: (myId: string) => AssignmentFilters }[] = [
  { label: 'All cases', view: () => ({ assigned_to_user_id: null, unassigned: false }) },
  { label: 'Assigned to me', view: (myId) => ({ assigned_to_user_id: myId, unassigned: false }) },
  { label: 'Unassigned', view: () => ({ assigned_to_user_id: null, unassigned: true }) },
]

function sameAssignment(filters: CaseFilters, view: AssignmentFilters): boolean {
  return (
    filters.assigned_to_user_id === view.assigned_to_user_id &&
    filters.unassigned === view.unassigned
  )
}

/** The handler's queue. Filters and page live in the URL, so a view can be bookmarked, shared,
 * or opened from a number on the dashboard. */
export function CaseListPage() {
  const user = useCurrentUser()
  const [params, setParams] = useSearchParams()
  const filters = parseFilters(params)
  const offset = parseOffset(params)
  const cases = useCases(filters, offset)
  const described = describeFilters(filters)
  // The case page's "back" link returns to exactly this view: filters, status and page.
  const fromList: FromList = { listSearch: params.toString() }

  /** Changing the status or the page keeps every other filter. */
  function show(next: { status?: CaseStatus | null; offset?: number }) {
    const { offset: nextOffset = offset, ...changed } = next
    setParams(filtersToSearch({ ...filters, ...changed }, nextOffset))
  }

  function applyFilters(next: CaseFilters) {
    setParams(filtersToSearch(next))
  }

  function clearFilters() {
    setParams(filtersToSearch({ status: filters.status }))
  }

  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">Complaint workspace</p>
          <h1>Cases</h1>
          <p className="muted">Review complaints, track deadlines and see who is responsible.</p>
        </div>
        <Link className="button primary new-case-action" to="/cases/new">
          New complaint
        </Link>
      </div>

      <div className="filter-card">
        <CaseSearch filters={filters} onChange={applyFilters} />
        <section className="queue-toolbar" aria-label="Case filters">
          <div className="queue-views" role="group" aria-label="Assignment">
            {ASSIGNMENT_VIEWS.map(({ label, view }) => (
              <button
                key={label}
                type="button"
                aria-pressed={sameAssignment(filters, view(user.id))}
                onClick={() => setParams(filtersToSearch({ ...filters, ...view(user.id) }))}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="inline">
            Status
            <select
              value={filters.status ?? ''}
              onChange={(event) => show({ status: parseStatus(event.target.value), offset: 0 })}
            >
              <option value="">All</option>
              {optionsOf(STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </section>
        <SavedViews filters={filters} onChange={applyFilters} />
      </div>

      {described.length > 0 && (
        <section className="active-filters" aria-label="Active filters">
          <span>Showing:</span>
          <ul>
            {described.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <button type="button" className="link-button" onClick={clearFilters}>
            Clear filters
          </button>
          {user.role === 'team_lead' && <Link to="/dashboard">Back to the dashboard</Link>}
        </section>
      )}

      {cases.isPending && <p>Loading cases…</p>}
      {cases.isError && <ErrorMessage error={cases.error} />}
      {cases.data && cases.data.total === 0 && (
        <p>{described.length > 0 ? 'No cases match these filters.' : 'No cases.'}</p>
      )}
      {cases.data && cases.data.total > 0 && cases.data.items.length === 0 && (
        // A bookmark to a page that no longer exists (cases were closed since): offer a way back.
        <p>
          This page is past the end of the list.{' '}
          <button type="button" className="link-button" onClick={() => show({ offset: 0 })}>
            Go to the first page
          </button>
        </p>
      )}
      {cases.data && cases.data.items.length > 0 && (
        <>
          <div className="queue-results">
            <strong>{plural(cases.data.total, 'case')}</strong>
            <span>
              <i aria-hidden="true" /> Updates automatically
            </span>
          </div>
          <div className="table-scroll case-table-wrap">
            <table className="cases">
              <thead>
                <tr>
                  <th scope="col" className="case-column">
                    Case / subject
                  </th>
                  <th scope="col">Status</th>
                  <th scope="col">Assigned to</th>
                  <th scope="col">Summary resolution</th>
                  <th scope="col">Final response</th>
                  <th scope="col">Vulnerability</th>
                </tr>
              </thead>
              <tbody>
                {cases.data.items.map((item) => (
                  <tr key={item.id}>
                    <td className="case-column">
                      <Link className="case-reference" to={`/cases/${item.id}`} state={fromList}>
                        {item.reference}
                      </Link>
                      <Link className="case-subject" to={`/cases/${item.id}`} state={fromList}>
                        {item.subject}
                      </Link>
                      <span className="case-received">
                        Received {formatDateTime(item.received_at)}
                      </span>
                    </td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>
                      <CaseOwner item={item} />
                    </td>
                    <td>
                      <DeadlineBadge progress={item.deadline_tracking?.src} />
                    </td>
                    <td>
                      <DeadlineBadge progress={item.deadline_tracking?.final_response} />
                    </td>
                    <td>
                      <FlagCount count={item.open_vulnerability_flags} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="pager" aria-label="Pages">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => show({ offset: Math.max(0, offset - PAGE_SIZE) })}
            >
              Previous
            </button>
            <span>
              {offset + 1}–{offset + cases.data.items.length} of {cases.data.total}
            </span>
            <button
              type="button"
              disabled={offset + PAGE_SIZE >= cases.data.total}
              onClick={() => show({ offset: offset + PAGE_SIZE })}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </>
  )
}

function CaseOwner({ item }: { item: CaseSummary }) {
  const name = item.assigned_to_display_name
  return (
    <div className={`case-owner${item.assigned_to_user_id ? '' : ' case-owner-empty'}`}>
      <span className="case-owner-avatar" aria-hidden="true">
        {name ? initials(name) : '—'}
      </span>
      <span>{assigneeLabel(item)}</span>
    </div>
  )
}
