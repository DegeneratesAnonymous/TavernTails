import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

interface ParticleContextValue {
  /** Current intensity 0 (resting) → 1 (peak). */
  intensity: number
  /** Clamp-safe setter — values outside [0, 1] are clamped. */
  setIntensity: (v: number) => void
}

const ParticleContext = createContext<ParticleContextValue>({
  intensity: 0,
  setIntensity: () => {},
})

export function ParticleProvider({ children }: { children: React.ReactNode }) {
  const [intensity, setIntensityRaw] = useState(0)

  const setIntensity = useCallback((v: number) => {
    setIntensityRaw(Math.max(0, Math.min(1, v)))
  }, [])

  return (
    <ParticleContext.Provider value={{ intensity, setIntensity }}>
      {children}
    </ParticleContext.Provider>
  )
}

/**
 * Read the current particle intensity and control it.
 *
 * Usage — driving intensity from component state:
 *   const { setIntensity } = useParticles()
 *   useEffect(() => { setIntensity(progress / total) }, [progress])
 */
export function useParticles() {
  return useContext(ParticleContext)
}

/**
 * Convenience hook: sets intensity to `value` while mounted, resets to 0 on unmount.
 * Pass a deps array to re-evaluate.
 *
 * Usage:
 *   useParticleIntensity(filledFields / totalFields, [filledFields])
 */
export function useParticleIntensity(value: number, deps: React.DependencyList = []) {
  const { setIntensity } = useParticles()
  const prev = useRef(0)

  useEffect(() => {
    const clamped = Math.max(0, Math.min(1, value))
    if (clamped !== prev.current) {
      prev.current = clamped
      setIntensity(clamped)
    }
    return () => {
      prev.current = 0
      setIntensity(0)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
