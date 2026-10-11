import { type FormEvent, useState } from 'react'

import { useDeleteView, useSavedViews, useSaveView } from '../../api/hooks'
import type { SavedView } from '../../api/types'
import { useCurrentUser } from '../../auth/authContext'
import { SearchIcon } from '../../shared/icons'
import { ErrorMessage } from '../../shared/Layout'
import { type CaseFilters, NO_FILTERS, filtersToSearch, parseFilters } from '../caseFilters'

interface FiltersProps {
  filters: CaseFilters
  onChange: (filters: CaseFilters) => void
}

/** Text and date search. The other filters stay as they are. */
export function CaseSearch({ filters, onChange }: FiltersProps) {
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const text = (field: string) => String(form.get(field) ?? '').trim() || null
    onChange({ ...filters, q: text('q'), received_from: text('from'), received_to: text('to') })
  }

  return (
    // `key`: Back/Forward or a saved view changes the URL; the fields must follow it.
    <form
      className="search-form"
      role="search"
      onSubmit={search}
      key={`${filters.q}-${filters.received_from}-${filters.received_to}`}
    >
      <label className="search-field">
        Search cases
        <SearchIcon />
        <input
          name="q"
          type="search"
          placeholder="Reference, subject or complaint text"
          maxLength={200}
          defaultValue={filters.q ?? ''}
        />
      </label>
      <label>
        Received from (UTC)
        <input name="from" type="date" defaultValue={filters.received_from ?? ''} />
      </label>
      <label>
        Received through (UTC)
        <input name="to" type="date" defaultValue={filters.received_to ?? ''} />
      </label>
      <button type="submit">Search</button>
    </form>
  )
}

/** One-click views: the handler's overdue cases, and the filter combinations they saved. */
export function SavedViews({ filters, onChange }: FiltersProps) {
  const user = useCurrentUser()
  const views = useSavedViews()
  const save = useSaveView()
  const remove = useDeleteView()
  const [name, setName] = useState('')

  function saveView(event: FormEvent) {
    event.preventDefault()
    save.mutate({ name: name.trim(), filters }, { onSuccess: () => setName('') })
  }

  const myOverdue: CaseFilters = {
    ...NO_FILTERS,
    assigned_to_user_id: user.id,
    open: true,
    deadline: 'final_response',
    deadline_risk: 'overdue',
  }

  return (
    <>
      <div className="saved-views" aria-label="Saved views">
        <span className="saved-views-label">Views</span>
        <button type="button" onClick={() => onChange(myOverdue)}>
          My overdue cases
        </button>
        {views.data?.map((view) => (
          <span key={view.id} className="saved-view">
            <button type="button" onClick={() => onChange(fromSavedView(view.filters))}>
              {view.name}
            </button>
            <button
              type="button"
              aria-label={`Delete view ${view.name}`}
              disabled={remove.isPending}
              onClick={() => remove.mutate(view.id)}
            >
              ×
            </button>
          </span>
        ))}
        <form className="save-view-form" onSubmit={saveView}>
          <label className="visually-hidden" htmlFor="save-view-name">
            Save current filters
          </label>
          <input
            id="save-view-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={80}
            required
            placeholder="Name the current filters"
          />
          <button type="submit" className="secondary" disabled={save.isPending || !name.trim()}>
            Save view
          </button>
        </form>
      </div>
      {save.isError && <ErrorMessage error={save.error} />}
      {remove.isError && <ErrorMessage error={remove.error} />}
      {views.isError && <ErrorMessage error={views.error} />}
    </>
  )
}

/** A saved view comes from the server: read it like a URL, so unknown values are dropped. */
function fromSavedView(filters: SavedView['filters']): CaseFilters {
  return parseFilters(filtersToSearch(filters))
}
