import React from 'react';

import './App.css';
import './LoginSignup.css';
import LoginSignupAgent from './agents/LoginSignupAgent';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <LoginSignupAgent />
      </header>
    </div>
  );
}

export default App;
