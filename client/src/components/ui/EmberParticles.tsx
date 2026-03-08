/**
 * EmberParticles — animated floating embers / sparks backdrop.
 * Ported from the D&D background quiz reference design.
 *
 * Each particle is a small gold-tinted dot that floats upward from the
 * bottom of the viewport, fades in/out, and drifts slightly sideways.
 * Particles are DOM elements appended directly to document.body so
 * they sit behind all other content regardless of stacking context.
 */
import { useEffect } from 'react';
import './EmberParticles.css';

interface EmberConfig {
  /** Interval (ms) between spawning new particles. Default: 1200 */
  interval?: number;
  /** Number of particles to seed on mount. Default: 5 */
  initialCount?: number;
  /** How long each particle lives (ms) before being removed. Default: 22000 */
  lifetime?: number;
}

function spawnEmber(lifetime: number) {
  const el = document.createElement('div');
  el.className = 'tt-ember-particle';
  el.style.left = Math.random() * 100 + 'vw';
  // Vary duration so they don't all arrive at the same time
  el.style.animationDuration = (8 + Math.random() * 12) + 's';
  el.style.animationDelay = (Math.random() * 4) + 's';
  const size = (2 + Math.random() * 3) + 'px';
  el.style.width = size;
  el.style.height = size;
  document.body.appendChild(el);
  setTimeout(() => {
    if (el.parentNode) el.parentNode.removeChild(el);
  }, lifetime);
}

export default function EmberParticles({
  interval = 1200,
  initialCount = 5,
  lifetime = 22000,
}: EmberConfig) {
  useEffect(() => {
    // Seed a handful immediately so the page doesn't start bare
    for (let i = 0; i < initialCount; i++) {
      spawnEmber(lifetime);
    }

    const id = window.setInterval(() => spawnEmber(lifetime), interval);
    return () => {
      window.clearInterval(id);
      // Clean up any orphaned particles
      document.querySelectorAll('.tt-ember-particle').forEach(el => el.remove());
    };
  }, [interval, initialCount, lifetime]);

  // Renders nothing itself — particles are appended directly to body
  return null;
}
