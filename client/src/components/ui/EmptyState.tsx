import React from 'react'

type Props = {
  title: string
  description?: string
  actions?: React.ReactNode
}

export default function EmptyState({ title, description, actions }: Props) {
  return (
    <div className="empty-state">
      <div className="empty-state-title">{title}</div>
      {description ? <div className="empty-state-desc">{description}</div> : null}
      {actions ? <div className="empty-state-actions">{actions}</div> : null}
    </div>
  )
}
