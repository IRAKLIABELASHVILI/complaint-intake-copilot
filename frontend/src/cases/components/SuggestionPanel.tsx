import { useState } from 'react'

import { useDecideCategory, useDecidePriority } from '../../api/hooks'
import type { CaseDetail } from '../../api/types'
import { formatDateTime } from '../../shared/format'
import { CATEGORY_LABELS, PRIORITY_LABELS, optionsOf } from '../../shared/labels'
import { ErrorMessage, Panel } from '../../shared/Layout'

/**
 * The AI's suggestion next to what a person decides. Accepting copies the suggestion; choosing
 * another value overrides it. Both are audited, and the suggestion itself is never changed.
 */
export function SuggestionPanel({ detail, canDecide }: { detail: CaseDetail; canDecide: boolean }) {
  const suggestion = detail.suggestion
  const category = useDecideCategory(detail.id)
  const priority = useDecidePriority(detail.id)

  return (
    <Panel title="AI suggestion and your decision">
      {suggestion ? (
        <>
          <p className="summary">{suggestion.summary}</p>
          <p className="muted small">
            Suggested by {suggestion.provider} / {suggestion.model} on{' '}
            {formatDateTime(suggestion.created_at)}. A person makes the decision.
          </p>
        </>
      ) : (
        <p className="muted">No AI suggestion. Decide from the complaint itself.</p>
      )}

      <Decision
        label="Category"
        labels={CATEGORY_LABELS}
        suggested={suggestion?.suggested_category ?? null}
        decided={detail.final_category}
        canDecide={canDecide}
        mutation={category}
      />
      <Decision
        label="Priority"
        labels={PRIORITY_LABELS}
        suggested={suggestion?.suggested_priority ?? null}
        decided={detail.final_priority}
        canDecide={canDecide}
        mutation={priority}
      />
    </Panel>
  )
}

interface DecisionProps<Value extends string> {
  label: string
  labels: Record<Value, string>
  suggested: Value | null
  decided: Value | null
  canDecide: boolean
  mutation: { mutate: (value: Value) => void; isPending: boolean; error: unknown }
}

function Decision<Value extends string>(props: DecisionProps<Value>) {
  const { label, labels, suggested, decided, canDecide, mutation } = props
  const [choice, setChoice] = useState<Value | ''>(decided ?? suggested ?? '')
  const id = `decide-${label.toLowerCase()}`

  return (
    <div className="decision" role="group" aria-label={label}>
      <div className="decision-values">
        <span>
          <strong>{label}</strong>
        </span>
        <span>Suggested: {suggested ? labels[suggested] : '—'}</span>
        <span>
          Decided: {decided ? <strong>{labels[decided]}</strong> : <em>not yet</em>}
          {decided && suggested && decided !== suggested && ' (overrode the suggestion)'}
        </span>
      </div>
      {canDecide && (
        <div className="decision-actions">
          {suggested && decided !== suggested && (
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={() => {
                setChoice(suggested)
                mutation.mutate(suggested)
              }}
            >
              Accept suggestion
            </button>
          )}
          <label htmlFor={id} className="visually-hidden">
            {label}
          </label>
          <select id={id} value={choice} onChange={(e) => setChoice(e.target.value as Value)}>
            <option value="" disabled>
              Choose…
            </option>
            {optionsOf(labels).map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={mutation.isPending || choice === '' || choice === decided}
            onClick={() => choice !== '' && mutation.mutate(choice)}
          >
            Save {label.toLowerCase()}
          </button>
        </div>
      )}
      {mutation.error != null && <ErrorMessage error={mutation.error} />}
    </div>
  )
}
