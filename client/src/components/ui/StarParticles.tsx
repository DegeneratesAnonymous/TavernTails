import { useEffect, useRef } from 'react'
import { useTheme } from '../../contexts/ThemeContext'
import { useParticles } from '../../contexts/ParticleContext'

// More stars, subtle brightness — twinkle rate is very slow for a serene deep-space feel
const STAR_COUNT = 200
const STAR_COLORS = ['#ffffff', '#ffffff', '#ffffff', '#caf0f8', '#e0f4ff', '#d4f1f9']

/**
 * StarParticles — slow, subtle twinkling starfield for the sci-fi theme.
 * Stars are placed once on mount; ~45% twinkle gently, ~55% are static.
 * Intensity (0–1) from ParticleContext brightens/dims the whole field.
 */
export default function StarParticles() {
  const { theme } = useTheme()
  const { intensity } = useParticles()
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (theme !== 'scifi') return

    const container = document.createElement('div')
    container.className = 'tt-star-container'
    // Resting state: field is subtle; will be brightened by intensity effect below
    container.style.filter = 'brightness(0.60)'
    document.body.appendChild(container)
    containerRef.current = container

    for (let i = 0; i < STAR_COUNT; i++) {
      const el = document.createElement('div')
      const size = 0.6 + Math.random() * 1.6
      // 45% of stars twinkle, 55% are static — more static = more natural/subtle
      const twinkles = Math.random() > 0.55

      el.className = twinkles ? 'tt-star' : 'tt-star tt-star--static'
      el.style.left = Math.random() * 100 + 'vw'
      el.style.top = Math.random() * 100 + 'vh'
      el.style.width = size + 'px'
      el.style.height = size + 'px'
      el.style.background = STAR_COLORS[Math.floor(Math.random() * STAR_COLORS.length)]

      if (twinkles) {
        // Slow drift: 10–28 s per cycle (was 2–7 s)
        el.style.animationDuration = (10 + Math.random() * 18) + 's'
        el.style.animationDelay = -(Math.random() * 22) + 's'
        // Low opacity range for subtlety: dim 0.03–0.10, peak 0.18–0.36
        el.style.setProperty('--star-min', (0.03 + Math.random() * 0.07).toFixed(2))
        el.style.setProperty('--star-max', (0.18 + Math.random() * 0.18).toFixed(2))
      } else {
        // Static stars: very faint, 0.08–0.30 (was 0.25–0.70)
        el.style.opacity = (0.08 + Math.random() * 0.22).toFixed(2)
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

  // As progress intensity rises (0 → 1), brighten the starfield smoothly
  // brightness(0.60) at rest → brightness(1.40) at peak
  useEffect(() => {
    if (!containerRef.current) return
    const brightness = 0.60 + intensity * 0.80
    containerRef.current.style.filter = `brightness(${brightness.toFixed(2)})`
  }, [intensity])

  return null
}
