import { Link, useParams } from 'react-router'

import { useCase } from '../api/hooks'
import type { CaseDetail, CaseStatus } from '../api/types'
import { formatDateTime } from '../shared/format'
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
  const canDecide = DECIDABLE.has(detail.status)
  const analysing = detail.status === 'new' || detail.status === 'analysing'

  return (
    <>
      <p>
        <Link to="/cases">← All cases</Link>
      </p>
      <div className="page-title">
        <h1>
          {detail.reference} · {detail.subject}
        </h1>
        <StatusBadge status={detail.status} />
      </div>

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
