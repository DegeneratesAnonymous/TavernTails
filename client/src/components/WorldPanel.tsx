import React from 'react'
import './WorldPanel.css'

type Props = {
  campaignId?: string | null
  situation?: Record<string, any>
  worldClock?: Record<string, any>
  memoryUpdates?: Record<string, any> | null
}

function asList(value: any): any[] {
  return Array.isArray(value) ? value.filter(Boolean) : []
}

function label(value: any): string {
  return String(value || '').replace(/_/g, ' ')
}

export default function WorldPanel({ campaignId: _campaignId, situation = {}, worldClock = {}, memoryUpdates }: Props) {
  const visibleClues = asList(situation.visibleClues)
  const recentEvents = asList(situation.worldMoves)
  const threads = asList(situation.storyThreads).length ? asList(situation.storyThreads) : asList(situation.threads)
  const newLocations = asList(memoryUpdates?.new_locations)
  const updatedLocations = asList(memoryUpdates?.updated_locations)
  const threatUpdates = asList(memoryUpdates?.world_state_changes?.threat_updates)
  return (
    <div className="wp-root">
      <div className="wp-section">
        <div className="wp-heading">Current Location</div>
        <div className="wp-location">{situation.location || 'Unknown location'}</div>
        <div className="wp-clock">
          {worldClock.campaign_day ? <span>Day {worldClock.campaign_day}</span> : null}
          {worldClock.time_block ? <span>{label(worldClock.time_block)}</span> : null}
          {worldClock.weather ? <span>{label(worldClock.weather)}</span> : null}
          {worldClock.temperature ? <span>{label(worldClock.temperature)}</span> : null}
          {worldClock.threat_level ? <span>Threat: {label(worldClock.threat_level)}</span> : null}
        </div>
      </div>

      {situation.currentObjective || situation.stakes ? (
        <div className="wp-section">
          <div className="wp-heading">What Matters</div>
          {situation.currentObjective ? <p>{situation.currentObjective}</p> : null}
          {situation.stakes ? <p className="wp-emphasis">{situation.stakes}</p> : null}
        </div>
      ) : null}

      {visibleClues.length ? (
        <div className="wp-section">
          <div className="wp-heading">Known Clues</div>
          <ul className="wp-list">
            {visibleClues.slice(0, 8).map((item, idx) => <li key={idx}>{String(item)}</li>)}
          </ul>
        </div>
      ) : null}

      {recentEvents.length ? (
        <div className="wp-section">
          <div className="wp-heading">Recent Events</div>
          <ul className="wp-list">
            {recentEvents.slice(0, 6).map((item, idx) => <li key={idx}>{String(item)}</li>)}
          </ul>
        </div>
      ) : null}

      {threads.length ? (
        <div className="wp-section">
          <div className="wp-heading">Threads</div>
          <ul className="wp-list">
            {threads.slice(0, 6).map((item, idx) => {
              const title = typeof item === 'string' ? item : (item?.title || item?.name || 'Thread')
              const status = typeof item === 'object' ? item?.status : ''
              return <li key={idx}><strong>{title}</strong>{status ? <span> — {status}</span> : null}</li>
            })}
          </ul>
        </div>
      ) : null}

      {(newLocations.length || updatedLocations.length || threatUpdates.length) ? (
        <div className="wp-section">
          <div className="wp-heading">World Memory</div>
          <ul className="wp-list">
            {newLocations.map((item, idx) => <li key={`new-${idx}`}>New place: {String(item)}</li>)}
            {updatedLocations.map((item, idx) => <li key={`upd-${idx}`}>Updated place: {String(item)}</li>)}
            {threatUpdates.map((item, idx) => <li key={`thr-${idx}`}>{typeof item === 'string' ? item : JSON.stringify(item)}</li>)}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
