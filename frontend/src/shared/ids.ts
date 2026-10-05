/**
 * A random id for one submission. `crypto.randomUUID` only exists on secure pages (https or
 * localhost); on plain http it is missing, so fall back to the same strength from getRandomValues.
 */
export function newSubmissionId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}
