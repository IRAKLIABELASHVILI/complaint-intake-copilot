import { describe, expect, it } from 'vitest'

import { HttpStatus, fakeApi } from '../test/fakeApi'
import { HANDLER } from '../test/data'
import { ApiError, createApiClient, unwrap } from './client'

const BASE = 'http://test.local/api'

describe('API client', () => {
  it('sends the token as a bearer header', async () => {
    const api = fakeApi({ 'GET /me': () => HANDLER })
    const client = createApiClient(() => 'secret-token', api.fetch, BASE)

    await client.GET('/me')

    expect(api.requests[0]?.authorization).toBe('Bearer secret-token')
  })

  it('sends no header when signed out', async () => {
    const api = fakeApi({ 'GET /me': () => new HttpStatus(401, { detail: 'Missing bearer token' }) })
    const client = createApiClient(() => null, api.fetch, BASE)

    await client.GET('/me')

    expect(api.requests[0]?.authorization).toBeNull()
  })
})

describe('unwrap', () => {
  async function failWith(status: number, body: unknown): Promise<ApiError> {
    const api = fakeApi({ 'GET /me': () => new HttpStatus(status, body) })
    const client = createApiClient(() => 't', api.fetch, BASE)
    try {
      unwrap(await client.GET('/me'))
    } catch (error) {
      if (error instanceof ApiError) return error
    }
    throw new Error('expected an ApiError')
  }

  it('uses the API message when there is one', async () => {
    expect((await failWith(409, { detail: "Not while 'new'" })).message).toBe("Not while 'new'")
  })

  it('lists validation errors by field', async () => {
    const error = await failWith(422, {
      detail: [
        { loc: ['body', 'sender_email'], msg: 'not a valid email' },
        { loc: ['body', 'body'], msg: 'too short' },
      ],
    })
    expect(error.status).toBe(422)
    expect(error.message).toBe('sender_email: not a valid email; body: too short')
  })

  it('never shows raw server errors', async () => {
    expect((await failWith(500, 'Traceback ...')).message).toBe(
      'The server had a problem. Please try again.',
    )
  })
})
