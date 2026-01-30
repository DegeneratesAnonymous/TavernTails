import React from 'react'

type Props = {
  title: string
  subtitle?: string
  actions?: React.ReactNode
}

export default function PageHeader({ title, subtitle, actions }: Props) {
  return (
    <div className="page-header">
      <div className="stack" style={{ gap: 6, minWidth: 0 }}>
        <h2 className="page-title">{title}</h2>
        {subtitle ? <div className="page-subtitle">{subtitle}</div> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </div>
  )
}
