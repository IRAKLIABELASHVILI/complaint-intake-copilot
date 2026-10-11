import { useClaimCase } from '../../api/hooks'
import type { CaseDetail } from '../../api/types'
import { useCurrentUser } from '../../auth/authContext'
import { ErrorMessage } from '../../shared/Layout'
import { assigneeLabel } from '../assignee'

/** Who owns the case. An open case nobody owns can be claimed with one click. */
export function OwnershipBar({ detail }: { detail: CaseDetail }) {
  const user = useCurrentUser()
  const claim = useClaimCase(detail.id)
  const claimable = !detail.assigned_to_user_id && detail.status !== 'resolved'

  return (
    <section className="ownership-bar" aria-label="Case assignment">
      <div>
        <dl className="ownership-facts">
          <dt className="eyebrow">Assigned to</dt>
          <dd>{assigneeLabel(detail)}</dd>
        </dl>
        {detail.assigned_to_user_id === user.id && (
          <span className="ownership-you">Assigned to you</span>
        )}
      </div>
      {claimable && (
        <button
          type="button"
          className="primary"
          disabled={claim.isPending}
          onClick={() => claim.mutate(user.id)}
        >
          {claim.isPending ? 'Assigning…' : 'Assign to me'}
        </button>
      )}
      {claim.isError && <ErrorMessage error={claim.error} />}
    </section>
  )
}
