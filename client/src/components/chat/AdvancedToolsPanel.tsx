import React from 'react'

type AdvancedTool = {
  id: string
  label: string
  description: string
}

type Props = {
  tools: AdvancedTool[]
  disabled: boolean
  onRun: (toolId: string) => void
}

export default function AdvancedToolsPanel({ tools, disabled, onRun }: Props) {
  return (
    <div className="chat-panel stack">
      <div className="chat-panel-title">Session tools</div>
      <div className="stack" style={{ gap: 8 }}>
        {tools.map((tool) => (
          <div key={tool.id} className="chat-tool">
            <div className="chat-tool-main">
              <div className="chat-tool-label">{tool.label}</div>
              <div className="chat-tool-description">{tool.description}</div>
            </div>
            <button className="btn btn-sm btn-secondary" type="button" disabled={disabled} onClick={() => onRun(tool.id)}>
              Run
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
