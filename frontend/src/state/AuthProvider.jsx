import { useCallback, useEffect, useMemo, useState } from 'react'
import { AuthContext } from './authContext'

export default function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    fetch('/api/auth/me')
      .then(async (response) => {
        if (!response.ok) throw new Error('Could not check the current session.')
        return response.json()
      })
      .then((body) => { if (!cancelled) setUser(body.user || null) })
      .catch(() => { if (!cancelled) setUser(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const authenticate = useCallback(async (mode, fields) => {
    const response = await fetch(`/api/auth/${mode}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fields)
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || `Could not ${mode === 'signup' ? 'create your account' : 'sign in'}.`)
    setUser(body.user)
    return body.user
  }, [])

  const signOut = useCallback(async () => {
    await fetch('/api/auth/signout', { method: 'POST' }).catch(() => {})
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, authenticate, signOut }), [user, loading, authenticate, signOut])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
