type Props = {
  onClose?: () => void
  onOpenCharacters?: () => void
  onOpenDocuments?: () => void
}
export default function SiteMenu({
  onClose,
  onOpenCharacters,
  onOpenDocuments,
}: Props){
  return (
    <div className="site-menu-panel">
      <header className="site-menu-header">
        <div>
          <div className="site-menu-title">Panels</div>
          <div className="site-menu-subtitle">In-game controls and info</div>
        </div>
        <button className="site-menu-close" onClick={onClose} aria-label="Close menu">
          ✕
        </button>
      </header>

      <section className="site-menu-section">
        <div className="site-menu-section-title">Panels</div>
        <ul className="site-menu-list">
          {onOpenCharacters ? (
            <li>
              <button className="site-menu-item" onClick={onOpenCharacters}>
                <span className="site-menu-item-label">Party</span>
                <span className="site-menu-item-description">View party character sheets</span>
              </button>
            </li>
          ) : null}
          {onOpenDocuments ? (
            <li>
              <button className="site-menu-item" onClick={onOpenDocuments}>
                <span className="site-menu-item-label">Documents</span>
                <span className="site-menu-item-description">Notes, uploads, references</span>
              </button>
            </li>
          ) : null}
        </ul>
      </section>
    </div>
  )
}
