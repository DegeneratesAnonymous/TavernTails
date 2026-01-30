import React, { useEffect, useState } from 'react'

import Modal from '../ui/Modal'

type Props = {
  open: boolean
  onCancel: () => void
  onSubmit: (payload: { name: string; initiativeMod: number | null }) => void
}

export default function NpcSnapshotModal({ open, onCancel, onSubmit }: Props) {
  const [name, setName] = useState('')
  const [initiativeModText, setInitiativeModText] = useState('+0')

  useEffect(() => {
    if (!open) return
    setName('')
    setInitiativeModText('+0')
  }, [open])

  const parsedMod = (() => {
    const cleaned = initiativeModText.trim().replace(/[^0-9-+]/g, '')
    const n = parseInt(cleaned, 10)
    return Number.isNaN(n) ? null : n
  })()

  return (
    <Modal open={open} title="NPC Snapshot" onClose={onCancel}>
      <div className="stack">
        <div className="muted">Send a quick ping to the NPC agent for initiative cues.</div>

        <div className="stack" style={{ gap: 6 }}>
          <label className="muted">NPC name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Goblin Boss" autoFocus />
        </div>

        <div className="stack" style={{ gap: 6 }}>
          <label className="muted">Initiative modifier (optional)</label>
          <input className="input input-mono" value={initiativeModText} onChange={(e) => setInitiativeModText(e.target.value)} placeholder="+2" />
        </div>

        <div className="row-wrap" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" type="button" onClick={onCancel}>
            Cancel
          </button>
          <button
            className="btn"
            type="button"
            disabled={!name.trim()}
            onClick={() => onSubmit({ name: name.trim(), initiativeMod: parsedMod })}
          >
            Send
          </button>
        </div>
      </div>
    </Modal>
  )
}
