/**
 * Data access for the screens, built on TanStack Query: caching, loading and error states, and
 * refreshing what a change affects. Screens call these hooks; none of them talks to fetch directly.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

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
  cases: (status: CaseStatus | null, offset: number) => ['cases', status, offset] as const,
  allCases: ['cases'] as const,
  case: (id: string) => ['case', id] as const,
  audit: (id: string) => ['audit', id] as const,
}

/** While the worker is analysing, poll so the suggestions appear without a manual refresh. */
const ANALYSIS_POLL_MS = 2000
const STILL_ANALYSING: ReadonlySet<CaseStatus> = new Set(['new', 'analysing'])

export function useCases(status: CaseStatus | null, offset: number) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.cases(status, offset),
    queryFn: async () =>
      unwrap(
        await api.GET('/cases', {
          params: { query: { status: status ?? undefined, limit: PAGE_SIZE, offset } },
        }),
      ),
  })
}

export function useCase(caseId: string) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.case(caseId),
    queryFn: async () =>
      unwrap(await api.GET('/cases/{case_id}', { params: { path: { case_id: caseId } } })),
    refetchInterval: (query) =>
      query.state.data && STILL_ANALYSING.has(query.state.data.status) ? ANALYSIS_POLL_MS : false,
  })
}

export function useAuditTrail(caseId: string) {
  const api = useApi()
  return useQuery({
    queryKey: queryKeys.audit(caseId),
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
    },
  })
}

/** After any decision: the server returns the updated case; the audit trail and list changed too. */
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
