import React from 'react'
import { sourceTooltip } from '../../data/sourcebooks'

type Props = {
  source: string
  className?: string
  style?: React.CSSProperties
}

/**
 * Renders a D&D source reference (e.g. "EGtW 184") with a hover tooltip
 * showing the full book title and page number.
 */
export default function SourceRef({ source, className, style }: Props) {
  const tooltip = sourceTooltip(source)
  const hasTooltip = Boolean(tooltip && tooltip !== source)

  return (
    <span
      className={className}
      title={hasTooltip ? tooltip : undefined}
      style={{
        cursor: hasTooltip ? 'help' : undefined,
        borderBottom: hasTooltip ? '1px dotted currentColor' : undefined,
        opacity: 0.72,
        fontSize: '0.85em',
        ...style,
      }}
    >
      {source}
    </span>
  )
}
