import { Link, useLocation, useParams } from 'react-router'

import { useCase } from '../api/hooks'
import type { CaseDetail } from '../api/types'
import { formatDateTime } from '../shared/format'
import { ErrorMessage, Panel } from '../shared/Layout'
import { backToList } from './caseFilters'
import { Collaboration } from './components/Collaboration'
import { ResponseDrafts } from './components/ResponseDrafts'
import { AuditTrail } from './components/AuditTrail'
import { StatusBadge } from './components/badges'
import { ClosedBanner, CloseCasePanel } from './components/CaseClosure'
import { DeadlinesPanel } from './components/DeadlinesPanel'
import { IndicatorsPanel } from './components/IndicatorsPanel'
import { OwnershipBar } from './components/OwnershipBar'
import { SuggestionPanel } from './components/SuggestionPanel'

import { canDecide as canDecideCase, isAnalysing } from './status'

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
  const canDecide = canDecideCase(detail.status)
  const analysing = isAnalysing(detail.status)

  return (
    <>
      <p className="back-link">
        <Link to={back.to}>{back.label}</Link>
      </p>
      <header className="case-header">
        <div className="case-header-main">
          <div className="case-header-meta">
            <span className="case-reference-tag">{detail.reference}</span>
            <StatusBadge status={detail.status} />
          </div>
          <h1>{detail.subject}</h1>
        </div>
        <OwnershipBar detail={detail} />
      </header>
      {detail.status === 'resolved' && <ClosedBanner detail={detail} />}

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

      {/* Left: what the customer wrote and what the team does with it. Right: the decisions. */}
      <div className="detail-grid">
        <div>
          <Panel title="Complaint" className="complaint-letter">
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
          <ResponseDrafts caseId={detail.id} closed={detail.status === 'resolved'} />
          <Collaboration detail={detail} />
          <AuditTrail caseId={detail.id} />
        </div>
        <aside aria-label="Decisions">
          <DeadlinesPanel detail={detail} />
          {!analysing && <SuggestionPanel detail={detail} canDecide={canDecide} />}
          {!analysing && <IndicatorsPanel detail={detail} canDecide={canDecide} />}
          {canDecide && <CloseCasePanel caseId={detail.id} />}
        </aside>
      </div>
    </>
  )
}
