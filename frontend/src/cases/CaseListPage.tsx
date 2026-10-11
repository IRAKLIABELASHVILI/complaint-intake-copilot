import { Link, useSearchParams } from 'react-router'

import { PAGE_SIZE, useCases } from '../api/hooks'
import type { CaseStatus } from '../api/types'
import { useCurrentUser } from '../auth/authContext'
import { formatDateTime } from '../shared/format'
import { STATUS_LABELS, optionsOf, parseStatus } from '../shared/labels'
import { ErrorMessage } from '../shared/Layout'
import { type FromList, describeFilters, filtersToSearch, parseFilters } from './caseFilters'
import { DeadlineBadge, FlagCount, StatusBadge } from './components/badges'

/** The handler's queue. Filters and page live in the URL, so a view can be bookmarked, shared,
 * or opened from a number on the dashboard. */
export function CaseListPage() {
  const user = useCurrentUser()
  const [params, setParams] = useSearchParams()
  const filters = parseFilters(params)
  const offset = Math.max(0, Number(params.get('offset')) || 0)
  const cases = useCases(filters, offset)
  const described = describeFilters(filters)
  // The case page's "back" link returns to exactly this view: filters, status and page.
  const fromList: FromList = { listSearch: params.toString() }

  /** Changing the status or the page keeps every other filter. */
  function show(next: { status?: CaseStatus | null; offset?: number }) {
    const { offset: nextOffset = offset, ...changed } = next
    setParams(filtersToSearch({ ...filters, ...changed }, nextOffset))
  }

  function clearFilters() {
    setParams(filtersToSearch({ status: filters.status }))
  }

  return (
    <>
      <div className="page-title queue-heading">
        <div><p className="eyebrow">Complaint workspace</p><h1>Cases</h1><p className="queue-description">Review complaints, track deadlines and see who is responsible.</p></div>
        <Link className="new-case-action" to="/cases/new">+ New complaint</Link>
      </div>

      <section className="queue-toolbar" aria-label="Case filters">
        <div className="queue-views" role="group" aria-label="Assignment">
          <button type="button" aria-pressed={!filters.assigned_to_user_id && !filters.unassigned} onClick={() => setParams(filtersToSearch({ ...filters, assigned_to_user_id: null, unassigned: false }))}>All cases</button>
          <button type="button" aria-pressed={filters.assigned_to_user_id === user.id} onClick={() => setParams(filtersToSearch({ ...filters, assigned_to_user_id: user.id, unassigned: false }))}>Assigned to me</button>
          <button type="button" aria-pressed={filters.unassigned} onClick={() => setParams(filtersToSearch({ ...filters, assigned_to_user_id: null, unassigned: true }))}>Unassigned</button>
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
          <div className="queue-results"><strong>{cases.data.total} {cases.data.total === 1 ? 'case' : 'cases'}</strong><span><i aria-hidden="true" /> Updates automatically</span></div>
          <div className="table-scroll case-table-wrap">
          <table className="cases">
            <thead>
              <tr>
                <th scope="col" className="case-column">Case / subject</th>
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
                    <Link className="case-subject" to={`/cases/${item.id}`} state={fromList}>{item.subject}</Link>
                    <span className="case-received">Received {formatDateTime(item.received_at)}</span>
                  </td>
                  <td>
                    <StatusBadge status={item.status} />
                  </td>
                  <td>
                    <div className={`case-owner${item.assigned_to_user_id ? '' : ' case-owner-empty'}`}>
                      <span className="case-owner-avatar" aria-hidden="true">{item.assigned_to_display_name ? item.assigned_to_display_name.split(' ').map((part) => part[0]).slice(0, 2).join('') : '—'}</span>
                      <span>{item.assigned_to_display_name ?? (item.assigned_to_user_id ? 'Assigned user unavailable' : 'Unassigned')}</span>
                    </div>
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
