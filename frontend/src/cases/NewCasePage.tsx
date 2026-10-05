import { useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { ApiError } from '../api/client'
import { useCreateCase } from '../api/hooks'
import type { CaseCreate } from '../api/types'
import { ErrorMessage } from '../shared/Layout'
import { newSubmissionId } from '../shared/ids'

const FIELDS = {
  subject: 'Subject',
  body: 'Complaint',
  sender_email: 'Customer email',
  sender_name: 'Customer name (optional)',
  received_at: 'Received (optional, defaults to now)',
} as const

type Field = keyof typeof FIELDS

/** Log a complaint received by email or post. The analysis starts in the background at once. */
export function NewCasePage() {
  const create = useCreateCase()
  const navigate = useNavigate()
  const [form, setForm] = useState<Record<Field, string>>({
    subject: '',
    body: '',
    sender_email: '',
    sender_name: '',
    received_at: '',
  })
  // One id per filled-in form. Sent as the case's external_message_id, so the API's idempotency
  // turns a repeated submit (double click, network retry) into the same case, never a duplicate.
  const [submissionId] = useState(newSubmissionId)
  // Blocks a second submit at once: `isPending` only disables the button after a re-render.
  const submitting = useRef(false)

  function field(name: Field) {
    return {
      id: name,
      value: form[name],
      onChange: (event: { target: { value: string } }) =>
        setForm((current) => ({ ...current, [name]: event.target.value })),
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true
    const body: CaseCreate = {
      subject: form.subject,
      body: form.body,
      sender_email: form.sender_email,
      sender_name: form.sender_name || null,
      // <input type="datetime-local"> has no time zone: read it as this computer's local time.
      received_at: form.received_at ? new Date(form.received_at).toISOString() : null,
      external_message_id: `web-form:${submissionId}`,
    }
    create.mutate(body, {
      onSuccess: (created) => navigate(`/cases/${created.id}`),
      onSettled: () => {
        submitting.current = false
      },
    })
  }

  return (
    <>
      <h1>New complaint</h1>
      <form onSubmit={submit} className="panel form">
        <label htmlFor="subject">{FIELDS.subject}</label>
        <input {...field('subject')} required maxLength={500} />

        <label htmlFor="body">{FIELDS.body}</label>
        <textarea {...field('body')} required rows={10} maxLength={50000} />

        <label htmlFor="sender_email">{FIELDS.sender_email}</label>
        <input {...field('sender_email')} type="email" required />

        <label htmlFor="sender_name">{FIELDS.sender_name}</label>
        <input {...field('sender_name')} maxLength={200} />

        <label htmlFor="received_at">{FIELDS.received_at}</label>
        <input {...field('received_at')} type="datetime-local" />

        {create.error != null && <ErrorMessage error={inFormLanguage(create.error)} />}
        <button type="submit" disabled={create.isPending}>
          {create.isPending ? 'Saving…' : 'Create case'}
        </button>
      </form>
    </>
  )
}

/** Validation errors name fields as the API does ("body"); say them as this form does. */
function inFormLanguage(error: unknown): unknown {
  if (!(error instanceof ApiError) || error.fieldErrors.length === 0) return error
  const lines = error.fieldErrors.map(({ field, message }) => {
    const label = Object.hasOwn(FIELDS, field) ? FIELDS[field as Field].replace(/ \(.*\)$/, '') : field
    return `${label}: ${message}`
  })
  return new Error(lines.join('. '))
}
