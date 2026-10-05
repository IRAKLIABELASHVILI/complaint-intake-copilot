/**
 * The typed API client. Paths, parameters and responses all come from the backend's OpenAPI
 * description (src/api/schema.d.ts, generated): calling an endpoint that does not exist, or with
 * the wrong body, is a compile error.
 *
 * C# comparison: an NSwag-generated client, with the auth header added by a DelegatingHandler.
 */
import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from './schema'

/** All requests go to /api on our own origin: Vite (dev) or nginx (Docker) forwards them. */
export const API_BASE_URL = '/api'

export type ApiClient = ReturnType<typeof createClient<paths>>

/** One invalid field, as the API reported it: `field` is the API's name for it. */
export interface FieldError {
  field: string
  message: string
}

/** A failed API call, with a message that is safe and useful to show to the user. */
export class ApiError extends Error {
  readonly status: number
  /** For 422 validation errors: per field, so a form can use its own labels. */
  readonly fieldErrors: readonly FieldError[]

  constructor(status: number, message: string, fieldErrors: readonly FieldError[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

export function createApiClient(
  getToken: () => string | null,
  fetchImpl: (request: Request) => Promise<Response> = (request) => globalThis.fetch(request),
  baseUrl: string = API_BASE_URL, // tests need an absolute URL: Node has no page to resolve "/api"
): ApiClient {
  const client = createClient<paths>({ baseUrl, fetch: fetchImpl })
  const authorise: Middleware = {
    onRequest({ request }) {
      const token = getToken()
      if (token) request.headers.set('Authorization', `Bearer ${token}`)
      return request
    },
  }
  client.use(authorise)
  return client
}

/** Unwraps an openapi-fetch result: the data, or an ApiError with a readable message. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data !== undefined) return result.data
  const status = result.response.status
  const detail = (result.error as { detail?: unknown } | undefined)?.detail
  const fieldErrors = Array.isArray(detail) ? detail.map(toFieldError) : []
  throw new ApiError(status, describeError(status, detail, fieldErrors), fieldErrors)
}

/** FastAPI validation error: { loc: ["body", "field"], msg: "..." }. loc[0] says where the field
 * was (body, query, path); the rest is the field itself, which may well be called "body". */
function toFieldError(item: { loc?: unknown[]; msg?: string }): FieldError {
  return {
    field: (item.loc ?? []).slice(1).join('.'),
    // Pydantic prefixes custom checks with "Value error, ": not a phrase for users.
    message: (item.msg ?? 'Invalid').replace(/^Value error, /, ''),
  }
}

function describeError(status: number, detail: unknown, fieldErrors: FieldError[]): string {
  if (typeof detail === 'string') return detail
  if (fieldErrors.length > 0) {
    return fieldErrors
      .map(({ field, message }) => (field ? `${field}: ${message}` : message))
      .join('; ')
  }
  if (status === 401) return 'Your session is not valid. Please sign in again.'
  if (status >= 500) return 'The server had a problem. Please try again.'
  return `Request failed (${status})`
}
