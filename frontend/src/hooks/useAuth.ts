import { createContext, useContext } from 'react'
import type { User } from '../types'

export interface AuthContextType {
  user: User | null
  loading: boolean
  login: (token: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

// The provider component lives in components/auth/AuthProvider.tsx: a file
// that exports a component can't also export this hook (fast refresh).
export const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
