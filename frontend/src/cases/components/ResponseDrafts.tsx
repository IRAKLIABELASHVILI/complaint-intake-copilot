import { useState } from 'react'

import { useDrafts, useGenerateDraft, useUpdateDraft } from '../../api/hooks'
import type { Draft } from '../../api/types'
import { formatDateTime } from '../../shared/format'
import { ErrorMessage, Panel } from '../../shared/Layout'

/** The same gaps the API refuses to approve: privacy placeholders such as [NAME_1], and the
 * offline template's [Handler: ...] request for findings. */
const PLACEHOLDER = /\[(?:[A-Z]+(?:_[A-Z]+)*_\d+|Handler:[^\]]*)\]/g

function unfilledPlaceholders(body: string): string[] {
  return [...new Set(body.match(PLACEHOLDER) ?? [])]
}

/** AI-written replies to the customer. A person edits and approves; nothing is sent from here. */
export function ResponseDrafts({ caseId, closed }: { caseId: string; closed: boolean }) {
  const drafts = useDrafts(caseId)
  const generate = useGenerateDraft(caseId)

  return (
    <Panel title="Response drafts">
      <p className="hint">
        Review facts, wording and privacy placeholders before approving. Approval records your
        review; it does not send a message.
      </p>
      {!closed && (
        <button type="button" onClick={() => generate.mutate()} disabled={generate.isPending}>
          {generate.isPending ? 'Generating…' : 'Generate response draft'}
        </button>
      )}
      {generate.isError && <ErrorMessage error={generate.error} />}
      {drafts.isError && <ErrorMessage error={drafts.error} />}
      {drafts.data?.map((draft) => (
        // A new version (saved here or by a colleague) starts a fresh editor with its text.
        <DraftEditor
          key={`${draft.id}-${draft.version}`}
          draft={draft}
          caseId={caseId}
          closed={closed}
          onReload={() => void drafts.refetch()}
        />
      ))}
    </Panel>
  )
}

interface DraftEditorProps {
  draft: Draft
  caseId: string
  closed: boolean
  onReload: () => void
}

function DraftEditor({ draft, caseId, closed, onReload }: DraftEditorProps) {
  const save = useUpdateDraft(caseId, draft.id)
  const [body, setBody] = useState(draft.body)
  const [reviewed, setReviewed] = useState(false)
  const editable = !draft.approved_at && !closed
  const placeholders = unfilledPlaceholders(body)
  const canApprove = reviewed && placeholders.length === 0 && body.trim() !== ''

  return (
    <article className="draft-card">
      <p>
        <strong>{draft.approved_at ? 'Approved' : 'Awaiting human review'}</strong> ·{' '}
        {draft.provider === 'fake' ? 'Offline demo template' : 'AI generated'} ·{' '}
        {formatDateTime(draft.created_at)}
      </p>
      <label>
        Response text
        <textarea
          rows={9}
          maxLength={8000}
          value={body}
          readOnly={!editable}
          onChange={(event) => {
            setBody(event.target.value)
            setReviewed(false) // a changed text needs a fresh review
          }}
        />
      </label>
      {editable && (
        <>
          {placeholders.length > 0 && (
            <p className="notice warning" role="status">
              Fill in before approving: {placeholders.join(', ')}
            </p>
          )}
          <label className="inline">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(event) => setReviewed(event.target.checked)}
            />{' '}
            I have checked the facts, wording and placeholders.
          </label>
          <div className="inline">
            <button
              type="button"
              disabled={save.isPending || !body.trim()}
              onClick={() => save.mutate({ body, version: draft.version, approve: false })}
            >
              Save draft
            </button>
            <button
              type="button"
              disabled={save.isPending || !canApprove}
              onClick={() => save.mutate({ body, version: draft.version, approve: true })}
            >
              Approve response
            </button>
          </div>
        </>
      )}
      {draft.approved_at && (
        <p>Approved {formatDateTime(draft.approved_at)}. Ready for your normal sending process.</p>
      )}
      {save.isError && (
        <>
          <ErrorMessage error={save.error} />
          <button type="button" onClick={onReload}>
            Reload drafts
          </button>
        </>
      )}
    </article>
  )
}
