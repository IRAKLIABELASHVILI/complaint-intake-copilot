import { useEffect, useRef } from 'react'
import { Link } from 'react-router'

import { useNotifications } from '../api/hooks'
import type { DeadlineNotice } from '../api/types'
import { formatDateTime } from './format'
import { BellIcon } from './icons'
import { DEADLINE_LABELS, parseCode } from './labels'
import { ErrorMessage } from './Layout'

/** Deadlines that need attention, soonest first. One case can appear twice: once per deadline. */
export function Notifications() {
  const notices = useNotifications()
  const overdue = notices.data?.filter((notice) => notice.overdue).length ?? 0
  const panel = useRef<HTMLDetailsElement>(null)
  const close = () => panel.current?.removeAttribute('open')

  // A popup: a click elsewhere or Escape closes it, like any menu.
  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (!panel.current?.contains(event.target as Node)) close()
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [])

  return (
    <details className="notifications" ref={panel}>
      <summary>
        <BellIcon />
        Deadline alerts ({notices.data?.length ?? '…'})
        {overdue > 0 && <span className="notifications-overdue"> · {overdue} overdue</span>}
      </summary>
      {notices.isPending && <p>Loading alerts…</p>}
      {notices.isError && <ErrorMessage error={notices.error} />}
      {notices.data?.length === 0 && <p>No deadlines need attention.</p>}
      <ul>
        {notices.data?.map((notice) => (
          <li key={`${notice.case_id}-${notice.deadline}`}>
            <Link to={`/cases/${notice.case_id}`} onClick={close}>
              {notice.reference} · {notice.subject}
            </Link>
            <span className={notice.overdue ? 'error' : 'muted'}>{describe(notice)}</span>
          </li>
        ))}
      </ul>
    </details>
  )
}

function describe(notice: DeadlineNotice): string {
  const kind = parseCode(DEADLINE_LABELS, notice.deadline)
  const deadline = kind ? DEADLINE_LABELS[kind] : notice.deadline
  const state = notice.overdue ? 'overdue' : 'due soon'
  return `${deadline} ${state} · ${formatDateTime(notice.deadline_at)}`
}
