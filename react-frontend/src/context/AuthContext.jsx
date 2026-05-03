import { createContext, useContext, useEffect, useState } from 'react'
import { supabase } from '../utils/supabase'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session?.user) {
        setUser(data.session.user)
        loadProfile(data.session.user.email)
      } else {
        setLoading(false)
      }
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        setUser(session.user)
        loadProfile(session.user.email)
      } else {
        setUser(null)
        setProfile(null)
        setLoading(false)
      }
    })

    return () => listener.subscription.unsubscribe()
  }, [])

  async function loadProfile(email) {
    try {
      const { data } = await supabase
        .from('users')
        .select('*')
        .eq('email', email)
        .single()
      setProfile(data)
    } catch {
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }

  async function logout() {
    await supabase.auth.signOut()
    setUser(null)
    setProfile(null)
  }

  return (
    <AuthContext.Provider value={{ user, profile, loading, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
