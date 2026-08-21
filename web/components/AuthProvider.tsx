"use client"

import type { ReactNode } from "react"
import { createContext, useContext, useEffect, useState } from "react"
import { api, setAuthToken, type AuthResponse, type User } from "@/lib/api"

interface AuthContextValue {
  user: User | null
  token: string | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const stored = localStorage.getItem("intentlock_token")
    if (stored) {
      setAuthToken(stored)
      setToken(stored)
      api.auth.me()
        .then(setUser)
        .catch(() => {
          localStorage.removeItem("intentlock_token")
          setAuthToken(null)
          setToken(null)
        })
        .finally(() => setIsLoading(false))
    } else {
      setIsLoading(false)
    }
  }, [])

  const login = async (email: string, password: string) => {
    const response: AuthResponse = await api.auth.login({ email, password })
    setAuthToken(response.access_token)
    setToken(response.access_token)
    setUser(response.user)
    localStorage.setItem("intentlock_token", response.access_token)
  }

  const signup = async (email: string, password: string) => {
    const response: AuthResponse = await api.auth.register({ email, password })
    setAuthToken(response.access_token)
    setToken(response.access_token)
    setUser(response.user)
    localStorage.setItem("intentlock_token", response.access_token)
  }

  const logout = () => {
    localStorage.removeItem("intentlock_token")
    setAuthToken(null)
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}
