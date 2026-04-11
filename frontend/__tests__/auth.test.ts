/**
 * Tests for the getAuthHeaders utility (frontend/lib/auth.ts).
 */

import { getAuthHeaders } from '../lib/auth'

describe('getAuthHeaders', () => {
  beforeEach(() => {
    // Clear cookies between tests
    document.cookie = 'access_token=; max-age=0; path=/'
  })

  it('returns empty object when no access_token cookie is present', () => {
    expect(getAuthHeaders()).toEqual({})
  })

  it('returns Authorization Bearer header when access_token cookie is set', () => {
    document.cookie = 'access_token=my-jwt-token; path=/'
    expect(getAuthHeaders()).toEqual({ Authorization: 'Bearer my-jwt-token' })
  })

  it('handles token values that contain "=" characters (base64)', () => {
    document.cookie = 'access_token=abc.def==; path=/'
    expect(getAuthHeaders()).toEqual({ Authorization: 'Bearer abc.def==' })
  })

  it('returns empty object when access_token cookie value is empty', () => {
    document.cookie = 'access_token=; path=/'
    expect(getAuthHeaders()).toEqual({})
  })
})
