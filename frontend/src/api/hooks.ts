/**
 * Data access for the screens, built on TanStack Query: caching, loading and error states, and
 * refreshing what a change affects. Screens call these hooks; none of them talks to fetch directly.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { type CaseFilters, toApiQuery } from '../cases/caseFilters'
import { useApi } from './apiContext'
import { unwrap } from './client'
import type {
  CaseCreate,
  CaseDetail,
  CaseStatus,
  Category,
  IndicatorType,
  Priority,
} from './types'

export const PAGE_SIZE = 25

export const queryKeys = {
  cases: (filters: CaseFilters, offset: number) => ['cases', filters, offset] as const,
  allCases: ['cases'] as const,
  case: (id: string) => ['case', id] as const,
  audit: (id: string) => ['audit', id] as const,
  dashboard: ['dashboard'] as const,
}

// Pick up changes made by colleagues while this page is visible.
const CASE_REFRESH_MS = 5000
/** While the worker is analysing, poll so the suggestions appear without a manual refresh. */
const ANALYSIS_POLL_MS = 2000
const STILL_ANALYSING: ReadonlySet<CaseStatus> = new Set(['new', 'analysing'])

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
    refetchInterval: (query) =>
      query.state.data && STILL_ANALYSING.has(query.state.data.status) ? ANALYSIS_POLL_MS : CASE_REFRESH_MS,
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

export function useClaimCase(caseId: string) {
  const api = useApi()
  return useCaseDecision(caseId, async (userId: string) =>
    unwrap(await api.PATCH('/cases/{case_id}/assignment', {
      params: { path: { case_id: caseId } },
      body: { assigned_to_user_id: userId, only_if_unassigned: true },
    })),
  )
}


export function useResolveCase(caseId: string) {
  const api = useApi()
  return useCaseDecision(caseId, async (body: { resolution_type: 'src' | 'final_response'; note: string }) =>
    unwrap(await api.POST('/cases/{case_id}/resolve', { params: { path: { case_id: caseId } }, body })),
  )
}
