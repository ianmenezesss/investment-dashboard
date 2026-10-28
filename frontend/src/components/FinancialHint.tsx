import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

/** Compact help available by pointer, keyboard focus and touch; Escape dismisses it. */
export function FinancialHint({ label, children }: { label: string; children: string }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ left: 8, top: 8 })
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cancelClose = () => { if (closeTimer.current) clearTimeout(closeTimer.current); closeTimer.current = null }
  const scheduleClose = () => { cancelClose(); closeTimer.current = setTimeout(() => setOpen(false), 180) }
  useEffect(() => {
    if (!open) return
    const dismiss = (event: KeyboardEvent) => { if (event.key === 'Escape') { cancelClose(); setOpen(false) } }
    document.addEventListener('keydown', dismiss)
    return () => { document.removeEventListener('keydown', dismiss); cancelClose() }
  }, [open])
  const show = (button: HTMLButtonElement) => {
    const rect = button.getBoundingClientRect()
    setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - 328)),
      top: Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - 180)) })
    setOpen(true)
  }
  return <span className="financial-hint" onMouseEnter={cancelClose} onMouseLeave={scheduleClose}>
    <button type="button" aria-label={`Entender: ${label}`} aria-describedby={open ? id : undefined}
      onMouseEnter={e => { cancelClose(); show(e.currentTarget) }} onFocus={e => show(e.currentTarget)} onBlur={() => setOpen(false)} onClick={e => show(e.currentTarget)}
      onKeyDown={e => { if (e.key === 'Escape') { cancelClose(); setOpen(false); e.stopPropagation() } }}>ⓘ</button>
    {open && createPortal(<span id={id} className="financial-tooltip" role="tooltip" style={position} onMouseEnter={cancelClose} onMouseLeave={scheduleClose}>{children}</span>, document.body)}
  </span>
}
