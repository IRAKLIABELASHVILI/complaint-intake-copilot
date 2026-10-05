import type { CaseDetail, DeadlineProgress } from '../../api/types'
import { formatDateTime } from '../../shared/format'
import { Panel } from '../../shared/Layout'
import { DeadlineBadge } from './badges'

/** The two regulatory deadlines (FCA DISP), in UK time, with the business days left. */
export function DeadlinesPanel({ detail }: { detail: CaseDetail }) {
  const tracking = detail.deadline_tracking
  return (
    <Panel title="Deadlines">
      <dl className="facts stacked">
        <Deadline
          label="Summary resolution (3 business days)"
          at={detail.src_deadline_at}
          progress={tracking?.src}
        />
        <Deadline
          label="Final response (8 weeks)"
          at={detail.final_response_deadline_at}
          progress={tracking?.final_response}
        />
      </dl>
      {tracking?.resolved_in_time != null && (
        <p>{tracking.resolved_in_time ? 'Resolved in time.' : 'Resolved after the deadline.'}</p>
      )}
      {!tracking && <p className="muted">Deadlines are not available for this case.</p>}
    </Panel>
  )
}

function Deadline(props: {
  label: string
  at: string | null
  progress: DeadlineProgress | null | undefined
}) {
  return (
    <>
      <dt>{props.label}</dt>
      <dd>
        {props.at ? formatDateTime(props.at) : '—'} <DeadlineBadge progress={props.progress} />
      </dd>
    </>
  )
}
