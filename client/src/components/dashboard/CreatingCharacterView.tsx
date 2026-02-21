import React from 'react'

import PageHeader from '../ui/PageHeader'

type Props = {
  onDone: () => void
  onGoToImportPdf: () => void
  onGoToQuickCreate: () => void
  notificationsPending?: boolean
  onNotificationsClick?: () => void
}

export default function CreatingCharacterView({
  onDone,
  onGoToImportPdf,
  onGoToQuickCreate,
  notificationsPending,
  onNotificationsClick,
}: Props) {
  return (
    <section className="dashboard-panel stack">
      <PageHeader
        title="Creating a Character"
        subtitle="Use TavernTails with a quick, lightweight character, or import a D&D Beyond PDF/JSON export to populate details."
        actions={
          <button className="btn btn-quiet" type="button" onClick={onDone}>
            Done
          </button>
        }
      />

      <div className="card card-pad stack" style={{ maxWidth: 980 }}>
        <div style={{ fontWeight: 750 }}>Recommended: Import from D&D Beyond</div>
        <div className="muted" style={{ fontSize: 13 }}>
          If you already have a character in D&amp;D Beyond, download the PDF export and upload it here. TavernTails reads the fillable PDF field values (best-effort) and keeps the raw extracted data so we can improve parsing over time.
        </div>
        <div className="row-wrap">
          <button className="btn" type="button" onClick={onGoToImportPdf}>
            Upload DDB PDF
          </button>
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          Tip: In D&amp;D Beyond, open the character sheet and use Print/Export to download a PDF.
        </div>
      </div>

      <div className="card card-pad stack" style={{ maxWidth: 980 }}>
        <div style={{ fontWeight: 750 }}>Quick create in TavernTails</div>
        <div className="muted" style={{ fontSize: 13 }}>
          Create a minimal character (name, level, class) and start playing. You can import richer data later.
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
