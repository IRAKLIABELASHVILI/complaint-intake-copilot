import { Link, useSearchParams } from 'react-router'

import { PAGE_SIZE, useCases } from '../api/hooks'
import type { CaseStatus } from '../api/types'
import { formatDateTime } from '../shared/format'
import { STATUS_LABELS, optionsOf, parseStatus } from '../shared/labels'
import { ErrorMessage } from '../shared/Layout'
import { DeadlineBadge, FlagCount, StatusBadge } from './components/badges'

/** The handler's queue. Filter and page live in the URL, so a view can be bookmarked or shared. */
export function CaseListPage() {
  const [params, setParams] = useSearchParams()
  const status = parseStatus(params.get('status'))
  const offset = Math.max(0, Number(params.get('offset')) || 0)
  const cases = useCases(status, offset)

  function show(next: { status?: CaseStatus | null; offset?: number }) {
    const merged = { status, offset, ...next }
    const query: Record<string, string> = {}
    if (merged.status) query.status = merged.status
    if (merged.offset) query.offset = String(merged.offset)
    setParams(query)
  }

  return (
    <>
      <div className="page-title">
        <h1>Cases</h1>
        <label className="inline">
          Status
          <select
            value={status ?? ''}
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
      </div>

      {cases.isPending && <p>Loading cases…</p>}
      {cases.isError && <ErrorMessage error={cases.error} />}
      {cases.data && cases.data.total === 0 && <p>No cases.</p>}
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
          <div className="table-scroll">
          <table className="cases">
            <thead>
              <tr>
                <th scope="col">Reference</th>
                <th scope="col">Subject</th>
                <th scope="col">Received</th>
                <th scope="col">Status</th>
                <th scope="col">Summary resolution</th>
                <th scope="col">Final response</th>
                <th scope="col">Vulnerability</th>
              </tr>
            </thead>
            <tbody>
              {cases.data.items.map((item) => (
                <tr key={item.id}>
                  <td className="nowrap">
                    <Link to={`/cases/${item.id}`}>{item.reference}</Link>
                  </td>
                  <td>{item.subject}</td>
                  <td className="nowrap">{formatDateTime(item.received_at)}</td>
                  <td>
                    <StatusBadge status={item.status} />
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
