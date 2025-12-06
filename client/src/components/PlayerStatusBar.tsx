import React from 'react'

type Props = {
  name: string
  ac: number
  hp: { current: number; max: number }
  tempHp?: number
  deathSaves: { success: number; failure: number }
  exhaustion: number
  spellSaveDc: number
}

export default function PlayerStatusBar({name, ac, hp, tempHp = 0, deathSaves, exhaustion, spellSaveDc}: Props){
  return (
    <section className="player-status" aria-label="Player stats">
      <div className="player-status-name">{name}</div>
      <div className="player-status-grid">
        <div>
          <div className="player-status-label">Armor Class</div>
          <div className="player-status-value">{ac}</div>
        </div>
        <div>
          <div className="player-status-label">Hit Points</div>
          <div className="player-status-value">{hp.current} / {hp.max}</div>
        </div>
        <div>
          <div className="player-status-label">Temp HP</div>
          <div className="player-status-value">{tempHp}</div>
        </div>
        <div>
          <div className="player-status-label">Death Saves</div>
          <div className="player-status-value successes">✔︎ {deathSaves.success} / ✖︎ {deathSaves.failure}</div>
        </div>
        <div>
          <div className="player-status-label">Exhaustion</div>
          <div className="player-status-value">{exhaustion}</div>
        </div>
        <div>
          <div className="player-status-label">Spell Save DC</div>
          <div className="player-status-value">{spellSaveDc}</div>
        </div>
      </div>
    </section>
  )
}
