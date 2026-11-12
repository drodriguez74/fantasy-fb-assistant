import { useState, useEffect, useCallback, ReactNode } from 'react'
import { auth } from '../../services/api'
import { AuthContext } from '../../hooks/useAuth'
import type { User } from '../../types'

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const login = async (token: string) => {
    localStorage.setItem('access_token', token)
    await refreshUser()
  }

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    setUser(null)
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      const response = await auth.getProfile()
      setUser(response.data)
    } catch (error) {
      console.error('Failed to refresh user:', error)
      logout()
    }
  }, [logout])

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('access_token')
      if (token) {
        await refreshUser()
      }
      setLoading(false)
    }

    initAuth()
  }, [refreshUser])

  const value = {
    user,
    loading,
    login,
    logout,
    refreshUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
