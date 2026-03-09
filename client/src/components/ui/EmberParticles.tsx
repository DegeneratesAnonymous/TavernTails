import { useEffect, useRef } from 'react'
import { useTheme } from '../../contexts/ThemeContext'

/**
 * EmberParticles — floating gold ember dots that rise from the bottom.
 * Only renders in the medieval theme.
 */
export default function EmberParticles() {
  const { theme } = useTheme()
  const containerRef = useRef<HTMLDivElement | null>(null)

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
      const size = 2 + Math.random() * 3
      el.style.left = Math.random() * 100 + 'vw'
      el.style.width = size + 'px'
      el.style.height = size + 'px'
      el.style.animationDuration = (9 + Math.random() * 11) + 's'
      el.style.animationDelay = (Math.random() * 3) + 's'
      el.style.opacity = '0'
      containerRef.current.appendChild(el)
      setTimeout(() => el.remove(), 24000)
    }

    // Seed initial embers
    for (let i = 0; i < 6; i++) spawnEmber()
    const interval = setInterval(spawnEmber, 1100)

    return () => {
      clearInterval(interval)
      if (containerRef.current) {
        containerRef.current.remove()
        containerRef.current = null
      }
    }
  }, [theme])

  return null
}
