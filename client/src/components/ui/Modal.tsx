import React, { useEffect } from 'react'
import ReactDOM from 'react-dom'

import './Modal.css'

type Props = {
  open: boolean
  title?: string
  children: React.ReactNode
  onClose: () => void
  className?: string
}

export default function Modal({ open, title, children, onClose, className }: Props) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  return ReactDOM.createPortal(
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={title || 'Dialog'} onMouseDown={onClose}>
      <div className={`modal${className ? ` ${className}` : ''}`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">{title || ''}</div>
          <button className="btn btn-quiet btn-sm" type="button" onClick={onClose} aria-label="Close dialog">
            Close
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>,
    document.body
  )
}
