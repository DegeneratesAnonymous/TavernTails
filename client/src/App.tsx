import React, { useMemo, useState } from 'react';

import './App.css';
import LoginSignupAgent from './agents/LoginSignupAgent';
import HomePage from './components/HomePage';
import { ThemeProvider } from './context/ThemeContext';
import EmberParticles from './components/ui/EmberParticles';

function AppInner() {
  const hasToken = useMemo(() => {
    if (typeof window === 'undefined') return false
    return Boolean(window.localStorage.getItem('access_token'))
  }, [])
  const [showAuth, setShowAuth] = useState(hasToken)
  const [initialMode, setInitialMode] = useState<'login' | 'signup'>('login')

  return (
    <div className="App">
      <EmberParticles />
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
  );
}

function App() {
  return (
    <ThemeProvider>
      <AppInner />
    </ThemeProvider>
  );
}

export default App;
