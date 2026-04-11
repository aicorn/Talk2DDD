/**
 * Reads the `access_token` cookie and returns an Authorization header object.
 * Returns an empty object when no token is present (e.g. during SSR or when
 * the user is logged out).
 */
export function getAuthHeaders(): Record<string, string> {
  if (typeof document === 'undefined') return {}
  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith('access_token='))
  if (!match) return {}
  const token = match.split('=').slice(1).join('=')
  return token ? { Authorization: `Bearer ${token}` } : {}
}
