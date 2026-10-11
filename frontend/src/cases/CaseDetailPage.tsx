import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'

import { useCase, useClaimCase, useResolveCase } from '../api/hooks'
import type { CaseDetail, CaseStatus } from '../api/types'
import { useCurrentUser } from '../auth/authContext'
import { formatDateTime } from '../shared/format'
import { backToList } from './caseFilters'
import { ErrorMessage, Panel } from '../shared/Layout'
import { AuditTrail } from './components/AuditTrail'
import { StatusBadge } from './components/badges'
import { DeadlinesPanel } from './components/DeadlinesPanel'
import { IndicatorsPanel } from './components/IndicatorsPanel'
import { SuggestionPanel } from './components/SuggestionPanel'

/** The same rule as the API's: decisions once the analysis is over, until the case is resolved. */
const DECIDABLE: ReadonlySet<CaseStatus> = new Set([
  'awaiting_review',
  'needs_human_review',
  'in_progress',
])

export function CaseDetailPage() {
  const { caseId = '' } = useParams()
  const query = useCase(caseId)

  if (query.isPending) return <p>Loading case…</p>
  if (query.isError) return <ErrorMessage error={query.error} />

  // `key`: a different case gets brand-new components. Without it, React reuses them when moving
  // between cases, and a half-made choice on one case (an unsaved category, a typed quote) would
  // appear on the next one, where a click on Save would record it against the wrong case.
  return <CaseView key={query.data.id} detail={query.data} />
}

function CaseView({ detail }: { detail: CaseDetail }) {
  const back = backToList(useLocation().state)
  const user = useCurrentUser()
  const claim = useClaimCase(detail.id)
  const resolve = useResolveCase(detail.id)
  const [closing, setClosing] = useState(false)
  const [note, setNote] = useState('')
  const [resolutionType, setResolutionType] = useState<'src' | 'final_response'>('final_response')
  const canDecide = DECIDABLE.has(detail.status)
  const analysing = detail.status === 'new' || detail.status === 'analysing'

  return (
    <>
      <p>
        <Link to={back.to}>{back.label}</Link>
      </p>
      <div className="case-heading">
        <div>
          <p className="eyebrow">{detail.reference}</p>
          <h1>{detail.subject}</h1>
        </div>
        <StatusBadge status={detail.status} />
      </div>
      <section className="ownership-bar" aria-label="Case assignment">
        <div>
          <dl className="ownership-facts">
            <dt className="eyebrow">Assigned to</dt>
            <dd>{detail.assigned_to_display_name ?? (detail.assigned_to_user_id ? 'Assigned user unavailable' : 'Unassigned')}</dd>
          </dl>
          {detail.assigned_to_user_id === user.id && <span className="ownership-you">Assigned to you</span>}
        </div>
        {!detail.assigned_to_user_id && detail.status !== 'resolved' && (
          <button type="button" disabled={claim.isPending} onClick={() => claim.mutate(user.id)}>
            {claim.isPending ? 'Assigning…' : 'Assign to me'}
          </button>
        )}
        {claim.isError && <ErrorMessage error={claim.error} />}
      </section>

      {detail.status === 'resolved' ? (
        <section className="resolution-banner" aria-label="Case closed"><strong>Case closed</strong><p>{detail.resolution_type === 'src' ? 'Summary resolution' : 'Final response'} · {detail.resolved_at ? formatDateTime(detail.resolved_at) : ''}</p><span>The resolution note is recorded in the audit trail.</span></section>
      ) : canDecide && (
        <section className="close-case-panel" aria-label="Close case">
          <div><h2>Ready to close this case?</h2><p>Record the outcome once the complaint has been handled.</p></div>
          {!closing ? <button type="button" onClick={() => setClosing(true)}>Close case</button> : (
            <form onSubmit={(event) => { event.preventDefault(); resolve.mutate({ resolution_type: resolutionType, note: note.trim() }) }}>
              <label>Resolution type<select value={resolutionType} onChange={(event) => setResolutionType(event.target.value as 'src' | 'final_response')}><option value="final_response">Final response</option><option value="src">Summary resolution</option></select></label>
              <label>Resolution note<textarea required maxLength={4000} rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Explain how the complaint was resolved…" /></label>
              <p className="hint">This records closure and stops the deadline countdown. It does not send a response to the customer.</p>
              <div className="resolution-actions"><button type="submit" disabled={resolve.isPending || !note.trim()}>{resolve.isPending ? 'Closing…' : 'Confirm closure'}</button><button type="button" disabled={resolve.isPending} onClick={() => setClosing(false)}>Cancel</button></div>
              {resolve.isError && <ErrorMessage error={resolve.error} />}
            </form>
          )}
        </section>
      )}

      {analysing && (
        <p className="notice" role="status">
          The AI analysis is running. Suggestions will appear here in a moment.
        </p>
      )}
      {detail.status === 'needs_human_review' && (
        <p className="notice warning" role="status">
          <strong>Needs a person:</strong> {detail.review_reason ?? 'the analysis did not finish.'}
        </p>
      )}

      <div className="detail-grid">
        <div>
          <Panel title="Complaint">
            <dl className="facts">
              <dt>From</dt>
              <dd>
                {detail.sender_name ? `${detail.sender_name} · ` : ''}
                {detail.sender_email}
              </dd>
              <dt>Received</dt>
              <dd>{formatDateTime(detail.received_at)}</dd>
            </dl>
            <p className="complaint-body">{detail.body}</p>
          </Panel>
          <AuditTrail caseId={detail.id} />
        </div>
        <div>
          <DeadlinesPanel detail={detail} />
          {!analysing && <SuggestionPanel detail={detail} canDecide={canDecide} />}
          {!analysing && <IndicatorsPanel detail={detail} canDecide={canDecide} />}
        </div>
      </div>
    </>
  )
}
