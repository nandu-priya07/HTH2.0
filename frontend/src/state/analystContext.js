import { createContext, useContext } from 'react'

export const AnalystContext = createContext(null)

export function useAnalyst() {
  const ctx = useContext(AnalystContext)
  if (!ctx) throw new Error('useAnalyst must be used inside <AnalystProvider>')
  return ctx
}
