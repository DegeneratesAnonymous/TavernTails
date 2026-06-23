import React from 'react'
import { sourceTooltip } from '../../data/sourcebooks'
import './SourceRef.css'

type Props = {
  source: string
  className?: string
  style?: React.CSSProperties
}

export default function SourceRef({ source, className, style }: Props) {
  const tooltip = sourceTooltip(source)
  const hasTooltip = Boolean(tooltip && tooltip !== source)

  return (
    <span
      className={`src-ref${className ? ` ${className}` : ''}`}
      data-tooltip={hasTooltip ? tooltip : undefined}
      style={{ opacity: 0.72, fontSize: '0.85em', ...style }}
    >
      {source}
    </span>
  )
}
