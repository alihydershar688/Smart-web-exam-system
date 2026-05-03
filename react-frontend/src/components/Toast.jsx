import { useState, useCallback } from 'react'

let toastFn = null

export function useToast() {
  const show = useCallback((message, type = 'info', duration = 3000) => {
    if (toastFn) toastFn(message, type, duration)
  }, [])
  return { show }
}

export function ToastContainer() {
  const [toasts, setToasts] = useState([])

  toastFn = (message, type, duration) => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration)
  }

  const colors = { success: '#22c55e', error: '#ef4444', info: '#3b82f6', warning: '#f59e0b' }

  return (
    <div style={{ position: 'fixed', top: 20, right: 20, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {toasts.map(t => (
        <div key={t.id} style={{
          background: '#1F2937', color: '#f8fafc', padding: '10px 14px', borderRadius: 8,
          borderLeft: `4px solid ${colors[t.type] || colors.info}`, fontSize: 14, fontWeight: 600,
          boxShadow: '0 8px 24px rgba(0,0,0,0.2)', minWidth: 260, maxWidth: 380,
          animation: 'slideIn 0.2s ease'
        }}>
          {t.message}
        </div>
      ))}
    </div>
  )
}
