import { type FormEvent, useState } from 'react'

import { useCaseNote, useUsers } from '../../api/hooks'
import type { CaseDetail } from '../../api/types'
import { ErrorMessage, Panel } from '../../shared/Layout'

/** Internal notes, and handing the case to a colleague with the reason as the note. */
export function Collaboration({ detail }: { detail: CaseDetail }) {
  const closed = detail.status === 'resolved'
  const users = useUsers()
  const save = useCaseNote(detail.id)
  const [note, setNote] = useState('')
  const [handTo, setHandTo] = useState('')
  // Handing a case to the person who already has it would change nothing.
  const colleagues = users.data?.filter((user) => user.id !== detail.assigned_to_user_id) ?? []

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate(
      { note: note.trim(), handTo: handTo || null },
      {
        onSuccess: () => {
          setNote('')
          setHandTo('')
        },
      },
    )
  }

  return (
    <Panel title="Internal notes and handover">
      <form onSubmit={submit}>
        <label>
          Internal note
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            required
            maxLength={4000}
            rows={3}
            placeholder="What you did, or why you are handing the case over…"
          />
        </label>
        {!closed && (
          <label>
            Hand over to (optional)
            <select value={handTo} onChange={(event) => setHandTo(event.target.value)}>
              <option value="">Add a comment only</option>
              {colleagues.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name}
                </option>
              ))}
            </select>
          </label>
        )}
        <p className="hint">
          Comments are internal: the customer never sees them. They appear in the case history.
        </p>
        <button type="submit" disabled={save.isPending || !note.trim()}>
          {save.isPending ? 'Saving…' : handTo ? 'Hand over with note' : 'Add comment'}
        </button>
        {save.isError && <ErrorMessage error={save.error} />}
        {users.isError && <ErrorMessage error={users.error} />}
      </form>
    </Panel>
  )
}
