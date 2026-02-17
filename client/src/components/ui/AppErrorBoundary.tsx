import React from 'react'

type Props = {
  children: React.ReactNode
}

type State = {
  error: Error | null
}

export default class AppErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Keep this visible in the console for debugging refresh/blank-screen issues.
    // eslint-disable-next-line no-console
    console.error('AppErrorBoundary caught an error', error, errorInfo)
  }

  render() {
    if (this.state.error) {
      const message = this.state.error.message || 'Unknown error'
      const stack = this.state.error.stack || ''
      return (
        <div
          style={{
            minHeight: '100vh',
            background: '#0b1220',
            color: '#e7eefc',
            padding: 24,
            fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif',
          }}
        >
          <div style={{ maxWidth: 980, margin: '0 auto' }}>
            <h1 style={{ margin: '0 0 8px 0', fontSize: 22 }}>TavernTails hit an error</h1>
            <p style={{ margin: '0 0 16px 0', opacity: 0.9 }}>
              The app crashed while rendering. Open DevTools → Console for details.
            </p>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <button
                className="btn"
                onClick={() => window.location.reload()}
                style={{ cursor: 'pointer' }}
              >
                Reload
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => this.setState({ error: null })}
                style={{ cursor: 'pointer' }}
              >
                Try to continue
              </button>
            </div>
            <div
              style={{
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.10)',
                borderRadius: 10,
                padding: 14,
                overflow: 'auto',
                maxHeight: '60vh',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 8 }}>{message}</div>
              {stack ? (
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', opacity: 0.9 }}>{stack}</pre>
              ) : null}
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
