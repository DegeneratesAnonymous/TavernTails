import React from 'react'
import './WorldPanel.css'

type Props = {
  campaignId?: string | null
}

export default function WorldPanel({ campaignId: _campaignId }: Props) {
  return (
    <div className="wp-root">
      <div style={{ padding: 16, opacity: 0.6 }}>World panel coming soon.</div>
    </div>
  )
}
