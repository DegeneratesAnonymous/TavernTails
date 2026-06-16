import React, { useEffect, useMemo, useState } from 'react';

import './App.css';
import './themes.css';
import { ThemeProvider } from './contexts/ThemeContext';
import LoginSignupAgent from './agents/LoginSignupAgent';
import HomePage from './components/HomePage';
import EmberParticles from './components/ui/EmberParticles';
import StarParticles from './components/ui/StarParticles';
import { buildApiUrl } from './api';

function App() {
  const hasToken = useMemo(() => {
    if (typeof window === 'undefined') return false
    return Boolean(window.localStorage.getItem('access_token'))
  }, [])
  const [showAuth, setShowAuth] = useState(hasToken)
  const [initialMode, setInitialMode] = useState<'login' | 'signup'>('login')

  // Detect Steward Dashboard SSO token in URL
  const [ssoLoading, setSsoLoading] = useState(() => {
    if (typeof window === 'undefined') return false
    return Boolean(new URLSearchParams(window.location.search).get('sso_token'))
  })

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const ssoToken = params.get('sso_token')
    if (!ssoToken) return
    // Strip token from URL immediately so it can't be reused via refresh
    window.history.replaceState({}, '', window.location.pathname)
    fetch(buildApiUrl('/player/steward-sso'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sso_token: ssoToken }),
    })
      .then(r => r.ok ? r.json() : Promise.reject('SSO failed'))
      .then(data => {
        if (data.access_token) {
          localStorage.setItem('access_token', data.access_token)
          setShowAuth(true)
        }
      })
      .catch(() => { /* SSO failed — fall through to normal login */ })
      .finally(() => setSsoLoading(false))
  }, [])

  if (ssoLoading) {
    return (
      <ThemeProvider>
        <EmberParticles />
        <StarParticles />
        <div className="App" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
          <p style={{ color: '#a78bfa', fontSize: '1.1rem', letterSpacing: '0.05em' }}>Connecting to Steward…</p>
        </div>
      </ThemeProvider>
    )
  }

  return (
    <ThemeProvider>
      <EmberParticles />
      <StarParticles />
      <div className="App">
        {showAuth ? (
          <LoginSignupAgent initialMode={initialMode} />
        ) : (
          <HomePage
            onGetStarted={() => {
              setInitialMode('login')
              setShowAuth(true)
            }}
            onSignIn={() => {
              setInitialMode('login')
              setShowAuth(true)
            }}
            onSignUp={() => {
              setInitialMode('signup')
              setShowAuth(true)
            }}
          />
        )}
      </div>
    </ThemeProvider>
  );
}

export default App;
