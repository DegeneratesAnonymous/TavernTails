import { useEffect, useRef } from 'react'
import { useTheme } from '../../contexts/ThemeContext'

const STAR_COUNT = 130
const STAR_COLORS = ['#ffffff', '#ffffff', '#ffffff', '#caf0f8', '#e0f4ff']

/**
 * StarParticles — twinkling starfield for the sci-fi theme.
 * Stars are placed once on mount; 65% twinkle, 35% are static.
 */
export default function StarParticles() {
  const { theme } = useTheme()
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (theme !== 'scifi') return

    const container = document.createElement('div')
    container.className = 'tt-star-container'
    document.body.appendChild(container)
    containerRef.current = container

    for (let i = 0; i < STAR_COUNT; i++) {
      const el = document.createElement('div')
      const size = 0.8 + Math.random() * 1.8
      const twinkles = Math.random() > 0.35

      el.className = twinkles ? 'tt-star' : 'tt-star tt-star--static'
      el.style.left = Math.random() * 100 + 'vw'
      el.style.top = Math.random() * 100 + 'vh'
      el.style.width = size + 'px'
      el.style.height = size + 'px'
      el.style.background = STAR_COLORS[Math.floor(Math.random() * STAR_COLORS.length)]

      if (twinkles) {
        el.style.animationDuration = (2 + Math.random() * 5) + 's'
        el.style.animationDelay = -(Math.random() * 6) + 's'
        el.style.setProperty('--star-min', (0.08 + Math.random() * 0.15).toFixed(2))
        el.style.setProperty('--star-max', (0.55 + Math.random() * 0.45).toFixed(2))
      } else {
        el.style.opacity = (0.25 + Math.random() * 0.45).toFixed(2)
      }

      container.appendChild(el)
    }

    return () => {
      if (containerRef.current) {
        containerRef.current.remove()
        containerRef.current = null
      }
    }
  }, [theme])

  return null
}
