import { type FormEvent, useState } from 'react'

import { useResolveCase } from '../../api/hooks'
import type { CaseDetail, ResolutionType } from '../../api/types'
import { formatDateTime } from '../../shared/format'
import { RESOLUTION_LABELS, parseCode } from '../../shared/labels'
import { ErrorMessage } from '../../shared/Layout'

/** How a resolved case was closed. The note itself is in the audit trail. */
export function ClosedBanner({ detail }: { detail: CaseDetail }) {
  const resolution = detail.resolution_type ? RESOLUTION_LABELS[detail.resolution_type] : ''
  const resolvedAt = detail.resolved_at ? formatDateTime(detail.resolved_at) : ''
  return (
    <section className="resolution-banner" aria-label="Case closed">
      <strong>Case closed</strong>
      <p>
        {resolution} · {resolvedAt}
      </p>
      <span>The resolution note is recorded in the audit trail.</span>
    </section>
  )
}

/** Record the outcome of a handled complaint. Asks for a note before anything is saved. */
export function CloseCasePanel({ caseId }: { caseId: string }) {
  const resolve = useResolveCase(caseId)
  const [closing, setClosing] = useState(false)
  const [resolutionType, setResolutionType] = useState<ResolutionType>('final_response')
  const [note, setNote] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    resolve.mutate({ resolution_type: resolutionType, note: note.trim() })
  }

  return (
    <section className="close-case-panel" aria-label="Close case">
      <div>
        <h2>Ready to close this case?</h2>
        <p>Record the outcome once the complaint has been handled.</p>
      </div>
      {!closing ? (
        <button type="button" onClick={() => setClosing(true)}>
          Close case
        </button>
      ) : (
        <form onSubmit={submit}>
          <label>
            Resolution type
            <select
              value={resolutionType}
              onChange={(event) => {
                const chosen = parseCode(RESOLUTION_LABELS, event.target.value)
                if (chosen) setResolutionType(chosen)
              }}
            >
              {/* Final response first: it is the usual way a case is closed. */}
              <option value="final_response">{RESOLUTION_LABELS.final_response}</option>
              <option value="src">{RESOLUTION_LABELS.src}</option>
            </select>
          </label>
          <label>
            Resolution note
            <textarea
              required
              maxLength={4000}
              rows={3}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Explain how the complaint was resolved…"
            />
          </label>
          <p className="hint">
            This records closure and stops the deadline countdown. It does not send a response to
            the customer.
          </p>
          <div className="resolution-actions">
            <button type="submit" disabled={resolve.isPending || !note.trim()}>
              {resolve.isPending ? 'Closing…' : 'Confirm closure'}
            </button>
            <button type="button" disabled={resolve.isPending} onClick={() => setClosing(false)}>
              Cancel
            </button>
          </div>
          {resolve.isError && <ErrorMessage error={resolve.error} />}
        </form>
      )}
    </section>
  )
}
