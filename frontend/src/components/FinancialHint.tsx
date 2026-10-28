import { useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'

/** Compact help available by pointer, keyboard focus and touch; Escape dismisses it. */
export function FinancialHint({ label, children }: { label: string; children: string }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ left: 8, top: 8 })
  useEffect(() => {
    if (!open) return
    const dismiss = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', dismiss)
    return () => document.removeEventListener('keydown', dismiss)
  }, [open])
  const show = (button: HTMLButtonElement) => {
    const rect = button.getBoundingClientRect()
    setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - 328)),
      top: Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - 180)) })
    setOpen(true)
  }
  return <span className="financial-hint" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
    <button type="button" aria-label={`Entender: ${label}`} aria-describedby={open ? id : undefined}
      onMouseEnter={e => show(e.currentTarget)} onFocus={e => show(e.currentTarget)} onBlur={() => setOpen(false)} onClick={e => show(e.currentTarget)}
      onKeyDown={e => { if (e.key === 'Escape') { setOpen(false); e.stopPropagation() } }}>ⓘ</button>
    {open && createPortal(<span id={id} className="financial-tooltip" role="tooltip" style={position}>{children}</span>, document.body)}
  </span>
}
