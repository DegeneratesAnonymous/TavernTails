import React from 'react'

import './HomePage.css'

type Props = {
  onGetStarted: () => void
  onSignIn: () => void
  onSignUp: () => void
}

export default function HomePage({ onGetStarted, onSignIn, onSignUp }: Props) {
  return (
    <div className="tt-home">
      <div className="tt-home-bg" />
      <div className="tt-home-content">
        <div className="tt-home-hero">
          <div className="tt-home-tag">TavernTails</div>
          <h1>Story-first AI GM, built for real tables.</h1>
          <p>
            Import characters, spin up campaigns, and keep the session moving with narrative cues,
            dice prompts, and live recap support.
          </p>
          <div className="tt-home-actions">
            <button className="btn" type="button" onClick={onGetStarted}>Get Started</button>
            <button className="btn btn-secondary" type="button" onClick={onSignIn}>Sign In</button>
            <button className="btn btn-ghost" type="button" onClick={onSignUp}>Create Account</button>
          </div>
        </div>

        <div className="tt-home-panels">
          <div className="card card-pad">
            <div className="muted">Character-first</div>
            <h3>Bring your characters</h3>
            <p>Import D&D Beyond PDFs/JSON, review the details, and manage the roster in one place.</p>
          </div>
          <div className="card card-pad">
            <div className="muted">Session-ready</div>
            <h3>Launch a campaign fast</h3>
            <p>Create a campaign, auto-generate a session, and start playing in minutes.</p>
          </div>
          <div className="card card-pad">
            <div className="muted">Always in sync</div>
            <h3>Real-time guidance</h3>
            <p>Scene cues, roll prompts, and notes recap keep everyone on the same page.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
