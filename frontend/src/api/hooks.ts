/**
 * Data access for the screens, built on TanStack Query: caching, loading and error states, and
 * refreshing what a change affects. Screens call these hooks; none of them talks to fetch directly.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { type CaseFilters, toApiQuery } from '../cases/caseFilters'
import { isAnalysing } from '../cases/status'
import { useApi } from './apiContext'
import { succeed, unwrap } from './client'
import type {
  AccountCreate,
  CaseCreate,
  CaseDetail,
  Category,
  IndicatorType,
  Priority,
  ResolutionType,
} from './types'

export const PAGE_SIZE = 25

export const queryKeys = {
  cases: (filters: CaseFilters, offset: number) => ['cases', filters, offset] as const,
  allCases: ['cases'] as const,
  case: (id: string) => ['case', id] as const,
  audit: (id: string) => ['audit', id] as const,
  drafts: (id: string) => ['drafts', id] as const,
  dashboard: ['dashboard'] as const,
  notifications: ['notifications'] as const,
  savedViews: ['saved-views'] as const,
  users: ['users'] as const,
}

/** Pick up changes made by colleagues (an assignment, a closure) while the page is open. */
const CASE_REFRESH_MS = 5000

/** While the worker is analysing, poll so the suggestions appear without a manual refresh. */
const ANALYSIS_POLL_MS = 2000

export function useCases(filters: CaseFilters, offset: number) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.cases(filters, offset),
    refetchInterval: CASE_REFRESH_MS,
    queryFn: async () =>
      unwrap(
        await api.GET('/cases', {
          params: { query: { ...toApiQuery(filters), limit: PAGE_SIZE, offset } },
        }),
      ),
  })
}

/** Countdowns move with the clock and cases keep arriving: refresh while the page is open. */
const DASHBOARD_REFRESH_MS = 5000

/** US-5. `enabled: false` for handlers: the API would answer 403, so do not even ask. */
export function useDashboard(enabled: boolean) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: async () => unwrap(await api.GET('/dashboard')),
    enabled,
    refetchInterval: DASHBOARD_REFRESH_MS,
  })
}

export function useCase(caseId: string) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.case(caseId),
    queryFn: async () =>
      unwrap(await api.GET('/cases/{case_id}', { params: { path: { case_id: caseId } } })),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && isAnalysing(status) ? ANALYSIS_POLL_MS : CASE_REFRESH_MS
    },
  })
}

export function useAuditTrail(caseId: string) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.audit(caseId),
    refetchInterval: CASE_REFRESH_MS,
    queryFn: async () =>
      unwrap(await api.GET('/cases/{case_id}/audit', { params: { path: { case_id: caseId } } })),
  })
}

export function useCreateCase() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: CaseCreate) => unwrap(await api.POST('/cases', { body })),
    onSuccess: (created) => {
      queryClient.setQueryData(queryKeys.case(created.id), created)
      void queryClient.invalidateQueries({ queryKey: queryKeys.allCases })
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard })
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
    },
  })
}

/** After any decision: the server returns the updated case; the audit trail, the lists and the
 * dashboard changed too. */
function useCaseDecision<Input>(
  caseId: string,
  send: (input: Input) => Promise<CaseDetail>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: send,
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.case(caseId), updated)
      void queryClient.invalidateQueries({ queryKey: queryKeys.audit(caseId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.allCases })
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard })
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
    },
  })
}

export function useDecideCategory(caseId: string) {
  const api = useApi()
  const path = { case_id: caseId }
  return useCaseDecision(caseId, async (category: Category) =>
    unwrap(await api.PUT('/cases/{case_id}/category', { params: { path }, body: { category } })),
  )
}

export function useDecidePriority(caseId: string) {
  const api = useApi()
  const path = { case_id: caseId }
  return useCaseDecision(caseId, async (priority: Priority) =>
    unwrap(await api.PUT('/cases/{case_id}/priority', { params: { path }, body: { priority } })),
  )
}

export function useDecideIndicator(caseId: string) {
  const api = useApi()
  return useCaseDecision(
    caseId,
    async ({ indicatorId, decision }: { indicatorId: string; decision: 'confirmed' | 'rejected' }) =>
      unwrap(
        await api.PUT('/cases/{case_id}/vulnerability-indicators/{indicator_id}/decision', {
          params: { path: { case_id: caseId, indicator_id: indicatorId } },
          body: { decision },
        }),
      ),
  )
}

export function useAddIndicator(caseId: string) {
  const api = useApi()
  return useCaseDecision(
    caseId,
    async (body: { indicator_type: IndicatorType; evidence_quote: string }) =>
      unwrap(
        await api.POST('/cases/{case_id}/vulnerability-indicators', {
          params: { path: { case_id: caseId } },
          body,
        }),
      ),
  )
}

/** "Assign to me". The API refuses (409) if a colleague claimed the case first. */
export function useClaimCase(caseId: string) {
  const api = useApi()
  return useCaseDecision(caseId, async (userId: string) =>
    unwrap(
      await api.PATCH('/cases/{case_id}/assignment', {
        params: { path: { case_id: caseId } },
        body: { assigned_to_user_id: userId, only_if_unassigned: true },
      }),
    ),
  )
}

export function useResolveCase(caseId: string) {
  const api = useApi()
  const path = { case_id: caseId }
  return useCaseDecision(
    caseId,
    async (body: { resolution_type: ResolutionType; note: string }) =>
      unwrap(await api.POST('/cases/{case_id}/resolve', { params: { path }, body })),
  )
}

// --- Team, alerts and personal views ------------------------------------------------------------

/** Colleagues in the same organisation: for handovers, names in the audit trail, and Accounts. */
export function useUsers(enabled = true) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.users,
    queryFn: async () => unwrap(await api.GET('/users')),
    enabled,
    staleTime: 60_000, // accounts change rarely
  })
}

export function useCreateAccount() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: AccountCreate) => unwrap(await api.POST('/users', { body })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.users }),
  })
}

/** Deadlines at risk or overdue: on the handler's own cases, or every case for a team lead. */
const NOTIFICATIONS_REFRESH_MS = 30_000

export function useNotifications() {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.notifications,
    queryFn: async () => unwrap(await api.GET('/notifications')),
    refetchInterval: NOTIFICATIONS_REFRESH_MS,
  })
}

export function useSavedViews() {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.savedViews,
    queryFn: async () => unwrap(await api.GET('/saved-views')),
  })
}

export function useSaveView() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ name, filters }: { name: string; filters: CaseFilters }) =>
      unwrap(
        await api.POST('/saved-views', {
          body: { name, filters },
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.savedViews }),
  })
}

export function useDeleteView() {
  const api = useApi()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (viewId: string) =>
      succeed(await api.DELETE('/saved-views/{view_id}', { params: { path: { view_id: viewId } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.savedViews }),
  })
}

// --- Collaboration on a case --------------------------------------------------------------------

/** What a note or handover changes: the case's owner, its history, the lists and the alerts. */
function useRefreshAfterCaseChange(caseId: string) {
  const queryClient = useQueryClient()
  return () => {
    for (const queryKey of [
      queryKeys.case(caseId),
      queryKeys.audit(caseId),
      queryKeys.drafts(caseId),
      queryKeys.allCases,
      queryKeys.dashboard,
      queryKeys.notifications,
    ]) {
      void queryClient.invalidateQueries({ queryKey })
    }
  }
}

/** An internal note, or, with `handTo`, a handover to that colleague with the note as reason. */
export function useCaseNote(caseId: string) {
  const api = useApi()
  const refresh = useRefreshAfterCaseChange(caseId)
  const path = { case_id: caseId }
  return useMutation({
    mutationFn: async ({ note, handTo }: { note: string; handTo: string | null }) => {
      if (handTo) {
        const body = { note, assigned_to_user_id: handTo }
        succeed(await api.POST('/cases/{case_id}/handoff', { params: { path }, body }))
      } else {
        unwrap(await api.POST('/cases/{case_id}/comments', { params: { path }, body: { note } }))
      }
    },
    onSuccess: refresh,
  })
}

export function useDrafts(caseId: string) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.drafts(caseId),
    queryFn: async () =>
      unwrap(await api.GET('/cases/{case_id}/drafts', { params: { path: { case_id: caseId } } })),
  })
}

export function useGenerateDraft(caseId: string) {
  const api = useApi()
  const refresh = useRefreshAfterCaseChange(caseId)
  return useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/cases/{case_id}/drafts', { params: { path: { case_id: caseId } } })),
    onSuccess: refresh,
  })
}

/** Save or approve. `version` is the one the handler edited: a colleague's newer save wins (409). */
export function useUpdateDraft(caseId: string, draftId: string) {
  const api = useApi()
  const refresh = useRefreshAfterCaseChange(caseId)
  return useMutation({
    mutationFn: async (body: { body: string; version: number; approve: boolean }) =>
      unwrap(
        await api.PUT('/cases/{case_id}/drafts/{draft_id}', {
          params: { path: { case_id: caseId, draft_id: draftId } },
          body,
        }),
      ),
    onSuccess: refresh,
  })
}
