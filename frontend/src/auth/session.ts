/**
 * Where the API token lives in the browser: sessionStorage, not localStorage, so it is gone when
 * the tab is closed. Storage can be unavailable (private windows, blocked site data), so every
 * access is guarded: the app then simply asks the user to sign in again.
 */
const TOKEN_KEY = 'cic.token'

export function readToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function saveToken(token: string): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Not fatal: the token still works for this page until it is reloaded.
  }
}

export function clearToken(): void {
  try {
    sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing to clear.
  }
}
