import { supabase } from './supabase'

export function getBackendBase() {
  const host = window.location.hostname
  if (host === 'localhost' || host === '127.0.0.1') {
    return 'http://127.0.0.1:5000/api'
  }
  return 'https://smart-web-exam-system.onrender.com/api'
}

export async function getAccessToken() {
  try {
    const { data } = await supabase.auth.getSession()
    return data?.session?.access_token || ''
  } catch {
    return ''
  }
}

export async function apiRequest(path, options = {}) {
  const token = await getAccessToken()
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  }
  const res = await fetch(`${getBackendBase()}${path}`, { ...options, headers })
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, status: res.status, data }
}
