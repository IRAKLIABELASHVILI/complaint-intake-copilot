/**
 * A fake backend for component tests: routes like "GET /cases/:id" answer with canned JSON, and
 * every request is recorded so a test can check exactly what the UI sent.
 * C# comparison: a fake HttpMessageHandler.
 */
/** A request body can be read only once: the fake reads it and passes it in, parsed. */
type Handler = (request: Request, params: Record<string, string>, body: unknown) => unknown

export interface Recorded {
  method: string
  path: string
  search: URLSearchParams
  authorization: string | null
  body: unknown
}

export class HttpStatus {
  readonly status: number
  readonly body: unknown

  constructor(status: number, body: unknown = {}) {
    this.status = status
    this.body = body
  }
}

export function fakeApi(routes: Record<string, Handler>) {
  const requests: Recorded[] = []
  const compiled = Object.entries(routes).map(([route, handler]) => {
    const [method, pattern = ''] = route.split(' ')
    const names: string[] = []
    const regex = new RegExp(
      '^' + pattern.replace(/:(\w+)/g, (_, name: string) => (names.push(name), '([^/]+)')) + '$',
    )
    return { method, regex, names, handler }
  })

  async function fetch(request: Request): Promise<Response> {
    const url = new URL(request.url)
    const path = url.pathname.replace(/^\/api/, '')
    const text = request.method === 'GET' ? '' : await request.text()
    const body: unknown = text ? JSON.parse(text) : undefined
    requests.push({
      method: request.method,
      path,
      search: url.searchParams,
      authorization: request.headers.get('Authorization'),
      body,
    })
    for (const route of compiled) {
      const match = route.method === request.method ? route.regex.exec(path) : null
      if (!match) continue
      const params = Object.fromEntries(route.names.map((name, i) => [name, match[i + 1] ?? '']))
      const result = route.handler(request, params, body)
      const status = result instanceof HttpStatus ? result.status : 200
      const payload = result instanceof HttpStatus ? result.body : result
      return new Response(JSON.stringify(payload), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    return new Response(JSON.stringify({ detail: `No fake route for ${request.method} ${path}` }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  return { fetch, requests }
}
