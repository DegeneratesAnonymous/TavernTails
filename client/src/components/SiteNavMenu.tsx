type Props = {
  onClose?: () => void
  onNavigate?: (key: string) => void
  isAdmin?: boolean
}

export default function SiteNavMenu({ onClose, onNavigate, isAdmin }: Props) {
  return (
    <div className="site-menu-panel">
      <header className="site-menu-header">
        <div>
          <div className="site-menu-title">Site</div>
          <div className="site-menu-subtitle">Navigate to other pages</div>
        </div>
        <button className="site-menu-close" onClick={onClose} aria-label="Close menu">
          ✕
        </button>
      </header>

      <section className="site-menu-section">
        <div className="site-menu-section-title">Navigate</div>
        <ul className="site-menu-list">
          <li>
            <button className="site-menu-item" onClick={() => onNavigate?.('campaign-setup')}>
              <span className="site-menu-item-label">Manage campaigns</span>
              <span className="site-menu-item-description">Create, configure, and start scenes</span>
            </button>
          </li>
          <li>
            <button className="site-menu-item" onClick={() => onNavigate?.('view-characters')}>
              <span className="site-menu-item-label">Manage characters</span>
              <span className="site-menu-item-description">Create, edit, and import</span>
            </button>
          </li>
          <li>
            <button className="site-menu-item" onClick={() => onNavigate?.('account')}>
              <span className="site-menu-item-label">Account</span>
              <span className="site-menu-item-description">Profile and sign out</span>
            </button>
          </li>
          {isAdmin && (
            <li>
              <button className="site-menu-item" onClick={() => onNavigate?.('admin')}>
                <span className="site-menu-item-label">Admin</span>
                <span className="site-menu-item-description">Site administration tools</span>
              </button>
            </li>
          )}
        </ul>
      </section>

      <section className="site-menu-section">
        <div className="site-menu-section-title">Account</div>
        <ul className="site-menu-list">
          <li>
            <button
              className="site-menu-item"
              onClick={() => {
                onClose?.()
                onNavigate?.('logout')
              }}
            >
              <span className="site-menu-item-label">Sign out</span>
              <span className="site-menu-item-description">Log out</span>
            </button>
          </li>
        </ul>
      </section>
    </div>
  )
}
