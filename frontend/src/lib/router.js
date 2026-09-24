/**
 * Minimal History-API router (no dependency).
 * Vite's dev/preview servers already fall back to index.html for unknown paths.
 */
import { useSyncExternalStore } from 'react'

const listeners = new Set()

function subscribe(cb) {
  listeners.add(cb)
  window.addEventListener('popstate', cb)
  return () => {
    listeners.delete(cb)
    window.removeEventListener('popstate', cb)
  }
}

const getPath = () => window.location.pathname.replace(/\/+$/, '') || '/'

export function navigate(to, { replace = false } = {}) {
  if (to === getPath()) return
  if (replace) window.history.replaceState({}, '', to)
  else window.history.pushState({}, '', to)
  listeners.forEach((cb) => cb())
  window.scrollTo({ top: 0 })
}

export function usePath() {
  return useSyncExternalStore(subscribe, getPath)
}
