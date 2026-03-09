import React, { useMemo, useState } from 'react';

import './App.css';
import './themes.css';
import { ThemeProvider } from './contexts/ThemeContext';
import LoginSignupAgent from './agents/LoginSignupAgent';
import HomePage from './components/HomePage';
import EmberParticles from './components/ui/EmberParticles';

function App() {
  const hasToken = useMemo(() => {
    if (typeof window === 'undefined') return false
    return Boolean(window.localStorage.getItem('access_token'))
  }, [])
  const [showAuth, setShowAuth] = useState(hasToken)
  const [initialMode, setInitialMode] = useState<'login' | 'signup'>('login')

  return (
    <ThemeProvider>
      <EmberParticles />
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
