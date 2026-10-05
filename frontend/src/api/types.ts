/** Friendly names for the generated API types. They change only when the backend's models do. */
import type { components } from './schema'

type Schemas = components['schemas']

export type User = Schemas['UserRead']
export type CaseSummary = Schemas['CaseSummary']
export type CaseList = Schemas['CaseList']
export type CaseDetail = Schemas['CaseRead']
export type CaseCreate = Schemas['CaseCreate']
export type CaseStatus = Schemas['CaseStatus']
export type Category = Schemas['Category']
export type Priority = Schemas['Priority']
export type Suggestion = Schemas['SuggestionRead']
export type Indicator = Schemas['IndicatorRead']
export type IndicatorType = Schemas['IndicatorType']
export type IndicatorDecision = Schemas['IndicatorDecision']
export type DeadlineProgress = Schemas['DeadlineProgressRead']
export type AuditEvent = Schemas['AuditEventRead']
export type VulnerabilityDriver = Schemas['VulnerabilityDriver']
