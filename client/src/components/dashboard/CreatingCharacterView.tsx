import React from 'react'
import { Sword } from 'lucide-react'

import PageHeader from '../ui/PageHeader'

type Props = {
  onDone: () => void
  onGoToImportPdf: () => void
  onGoToQuickCreate: () => void
  onGoToWizard?: () => void
  notificationsPending?: boolean
  onNotificationsClick?: () => void
}

export default function CreatingCharacterView({
  onDone,
  onGoToImportPdf,
  onGoToQuickCreate,
  onGoToWizard,
  notificationsPending,
  onNotificationsClick,
}: Props) {
  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title="Creating a Character"
        subtitle="Build a character from scratch with the guided wizard, import from D&D Beyond, or create a quick placeholder."
        actions={
          <button className="btn btn-quiet" type="button" onClick={onDone}>
            Done
          </button>
        }
      />

      {onGoToWizard && (
        <div className="card card-pad stack" style={{ maxWidth: 980 }}>
          <div style={{ fontWeight: 750, display: 'flex', alignItems: 'center', gap: 6 }}><Sword size={14} /> Recommended: Character Creation Wizard</div>
          <div className="muted" style={{ fontSize: 13 }}>
            Answer a few quick questions — pick your system, ancestry, class, and background through scenario-style choices.
            No spreadsheets, no wall of text. Works for all 10 supported game systems.
          </div>
          <div className="row-wrap">
            <button className="btn" type="button" onClick={onGoToWizard}>
              Launch Wizard
            </button>
          </div>
        </div>
      )}

      <div className="card card-pad stack" style={{ maxWidth: 980 }}>
        <div style={{ fontWeight: 750 }}>Import from D&D Beyond</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Already have a character in D&amp;D Beyond? Download the PDF export and upload it here. TavernTails reads the fillable PDF field values and keeps the raw data for future improvements.
        </div>
        <div className="row-wrap">
          <button className="btn btn-secondary" type="button" onClick={onGoToImportPdf}>
            Upload DDB PDF
          </button>
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          Tip: In D&amp;D Beyond, open the character sheet and use Print/Export to download a PDF.
        </div>
      </div>

      <div className="card card-pad stack" style={{ maxWidth: 980 }}>
        <div style={{ fontWeight: 750 }}>Quick create</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Create a minimal character (name, level, class) and start playing. You can add more detail later.
        </div>
        <div className="row-wrap">
          <button className="btn btn-secondary" type="button" onClick={onGoToQuickCreate}>
            Quick create
          </button>
        </div>
      </div>

      <div className="card card-pad stack" style={{ maxWidth: 980 }}>
        <div style={{ fontWeight: 750 }}>Helpful resources</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Official references for rules and basic character creation.
        </div>
        <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 8 }}>
          <li>
            <a href="https://www.dndbeyond.com/" target="_blank" rel="noreferrer">
              D&amp;D Beyond (character builder)
            </a>
          </li>
          <li>
            <a href="https://www.dndbeyond.com/sources/basic-rules" target="_blank" rel="noreferrer">
              D&amp;D Beyond Basic Rules
            </a>
          </li>
          <li>
            <a href="https://dnd.wizards.com/resources/systems-reference-document" target="_blank" rel="noreferrer">
              D&amp;D Systems Reference Document (SRD)
            </a>
          </li>
        </ul>
      </div>
    </section>
  )
}
