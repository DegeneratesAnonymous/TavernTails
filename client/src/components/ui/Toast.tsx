import React, { useEffect, useRef, useState } from 'react'

type Props = {
  message: string
  onDone: () => void
  duration?: number
}

/**
 * Center-screen toast notification.
 * Fades in on mount, dismisses after `duration` ms.
 * Hovering pauses the dismiss timer; it resumes on mouse-leave.
 */
export default function Toast({ message, onDone, duration = 3000 }: Props) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [dismissing, setDismissing] = useState(false)

  const startTimer = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setDismissing(true), duration)
  }

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  useEffect(() => {
    startTimer()
    return clearTimer
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      className={`tt-toast${dismissing ? ' tt-toast--dismissing' : ''}`}
      role="status"
      aria-live="polite"
      onMouseEnter={clearTimer}
      onMouseLeave={startTimer}
      onTransitionEnd={() => { if (dismissing) onDone() }}
    >
      {message}
    </div>
  )
}
