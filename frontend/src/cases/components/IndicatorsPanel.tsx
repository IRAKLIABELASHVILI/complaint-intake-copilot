import { useState, type FormEvent } from 'react'

import { useAddIndicator, useDecideIndicator } from '../../api/hooks'
import type { CaseDetail, IndicatorType } from '../../api/types'
import { DECISION_LABELS, DRIVER_LABELS, INDICATOR_LABELS, optionsOf } from '../../shared/labels'
import { ErrorMessage, Panel } from '../../shared/Layout'

/**
 * Vulnerability indicators (FCA FG21/1), each with the sentence that triggered it. Evidence is
 * rendered as plain text: React escapes it, so text from the complaint or the model can never
 * run as HTML in the handler's browser.
 */
export function IndicatorsPanel({ detail, canDecide }: { detail: CaseDetail; canDecide: boolean }) {
  const decide = useDecideIndicator(detail.id)
  const indicators = detail.vulnerability_indicators ?? []

  return (
    <Panel title="Vulnerability">
      {indicators.length === 0 && <p className="muted">No vulnerability indicators.</p>}
      <ul className="indicators">
        {indicators.map((indicator) => (
          <li key={indicator.id} className={`indicator decision-${indicator.decision}`}>
            <div className="indicator-head">
              <strong>{INDICATOR_LABELS[indicator.indicator_type]}</strong>
              <span className="muted">{DRIVER_LABELS[indicator.driver]}</span>
              <span className="badge">{DECISION_LABELS[indicator.decision]}</span>
              <span className="muted small">
                {indicator.source === 'ai' ? 'Suggested by AI' : 'Added by a handler'}
              </span>
            </div>
            <blockquote>{indicator.evidence_quote}</blockquote>
            {canDecide && (
              <div className="decision-actions">
                <button
                  type="button"
                  disabled={decide.isPending || indicator.decision === 'confirmed'}
                  onClick={() => decide.mutate({ indicatorId: indicator.id, decision: 'confirmed' })}
                >
                  Confirm
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={decide.isPending || indicator.decision === 'rejected'}
                  onClick={() => decide.mutate({ indicatorId: indicator.id, decision: 'rejected' })}
                >
                  Reject
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {decide.error != null && <ErrorMessage error={decide.error} />}
      {canDecide && <AddIndicatorForm caseId={detail.id} />}
    </Panel>
  )
}

function AddIndicatorForm({ caseId }: { caseId: string }) {
  const add = useAddIndicator(caseId)
  const [type, setType] = useState<IndicatorType | ''>('')
  const [quote, setQuote] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (type === '') return
    add.mutate(
      { indicator_type: type, evidence_quote: quote },
      {
        onSuccess: () => {
          setType('')
          setQuote('')
        },
      },
    )
  }

  return (
    <form onSubmit={submit} className="add-indicator">
      <h3>Add an indicator the AI missed</h3>
      <label htmlFor="indicator-type">Type</label>
      <select
        id="indicator-type"
        value={type}
        onChange={(event) => setType(event.target.value as IndicatorType)}
        required
      >
        <option value="" disabled>
          Choose…
        </option>
        {optionsOf(INDICATOR_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <label htmlFor="indicator-quote">Evidence: copy the words from the complaint</label>
      <textarea
        id="indicator-quote"
        rows={2}
        minLength={3}
        maxLength={500}
        value={quote}
        onChange={(event) => setQuote(event.target.value)}
        required
      />
      {add.error != null && <ErrorMessage error={add.error} />}
      <button type="submit" disabled={add.isPending || type === '' || quote.trim().length < 3}>
        Add indicator
      </button>
    </form>
  )
}
