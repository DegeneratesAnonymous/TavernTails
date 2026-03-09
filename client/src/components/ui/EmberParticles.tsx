import { useEffect, useRef } from 'react'
import { useTheme } from '../../contexts/ThemeContext'
import { useParticles } from '../../contexts/ParticleContext'

/**
 * EmberParticles — floating gold embers that rise from the bottom.
 * Only renders in the medieval theme.
 *
 * Responds to ParticleContext intensity (0–1):
 *   - intensity 0 → sparse, small, dim embers (resting state)
 *   - intensity 1 → dense, larger, bright embers (active/loading state)
 */
export default function EmberParticles() {
  const { theme } = useTheme()
  const { intensity } = useParticles()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Keep a live ref so the recursive scheduler always reads the latest intensity
  const intensityRef = useRef(intensity)

  useEffect(() => {
    intensityRef.current = intensity
  }, [intensity])

  useEffect(() => {
    if (theme !== 'medieval') return

    const container = document.createElement('div')
    container.className = 'tt-ember-container'
    document.body.appendChild(container)
    containerRef.current = container

    function spawnEmber() {
      if (!containerRef.current) return
      const el = document.createElement('div')
      el.className = 'tt-ember'
      const iv = intensityRef.current
      // Size: 1.5–3 px at rest, up to +2 px at peak intensity
      const size = 1.5 + Math.random() * 2.5 + iv * 2.0
      // Peak opacity: 0.55 at rest → 0.90 at peak
      const emberMax = (0.55 + iv * 0.35).toFixed(2)
      el.style.left = Math.random() * 100 + 'vw'
      el.style.width = size + 'px'
      el.style.height = size + 'px'
      el.style.animationDuration = (8 + Math.random() * 10) + 's'
      el.style.animationDelay = (Math.random() * 2) + 's'
      el.style.opacity = '0'
      // --ember-max drives keyframe opacity via CSS (see @keyframes tt-ember-rise)
      el.style.setProperty('--ember-max', emberMax)
      containerRef.current.appendChild(el)
      setTimeout(() => el.remove(), 22000)
    }

    // Seed initial embers
    for (let i = 0; i < 6; i++) spawnEmber()

    // Recursive scheduler: reads live intensity each cycle
    // Spawn interval: 1400 ms at rest (intensity=0) → 300 ms at peak (intensity=1)
    function scheduleNext() {
      const delay = Math.round(1400 - intensityRef.current * 1100)
      timeoutRef.current = setTimeout(() => {
        spawnEmber()
        scheduleNext()
      }, delay)
    }
    scheduleNext()

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      if (containerRef.current) {
        containerRef.current.remove()
        containerRef.current = null
      }
    }
  }, [theme])

  return null
}
