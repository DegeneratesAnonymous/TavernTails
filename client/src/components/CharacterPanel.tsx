import React, {useMemo, useRef, useState} from 'react'
import CharacterIconStrip, {CharacterSnapshot} from './CharacterIconStrip'
import './CharacterPanel.css'

type SectionKey = 'inventory' | 'spells' | 'skills'

export type SceneCue = {
  id: string
  prompt: string
  roll?: {
    type?: string
    skill?: string
    reason?: string
  }
}

export type CharacterSummary = CharacterSnapshot & {
  id: string
  name: string
  level: number
  hp: { current: number; max: number; temp?: number }
  ac: number
  spellSave: number
  inventory: string[]
  spells: string[]
}

type Props = {
  roster: CharacterSummary[]
  selectedId?: string | null
  onSelect?: (id: string) => void
  sceneCues?: SceneCue[]
  npcSpotlight?: {name: string; initiative_hint?: string}[]
  onCueRoll?: (cue: SceneCue) => Promise<void>
}

export default function CharacterPanel({roster, selectedId, onSelect, sceneCues = [], npcSpotlight = [], onCueRoll}: Props){
  const [expanded, setExpanded] = useState<SectionKey|null>(null)
  const containerRef = useRef<HTMLDivElement|null>(null)
  const [rollingCueId, setRollingCueId] = useState<string | null>(null)
  const [cueError, setCueError] = useState<string | null>(null)

  function toggle(key:SectionKey){
    setExpanded(prev => prev===key? null : key)
    // after open, ensure the panel scrolls so the expanded section is visible
    setTimeout(()=>{
      const el = document.getElementById('section-'+key)
      if(el) el.scrollIntoView({behavior:'smooth',block:'nearest'})
      if(containerRef.current) containerRef.current.scrollTop = containerRef.current.scrollHeight
    },120)
  }

  const selected = useMemo(() => {
    if(!roster.length) return undefined
    if(!selectedId) return roster[0]
    return roster.find(r => r.id === selectedId) ?? roster[0]
  }, [roster, selectedId])

  async function handleCueRoll(cue: SceneCue){
    if(!onCueRoll || !cue.roll) return
    setCueError(null)
    setRollingCueId(cue.id)
    try{
      await onCueRoll(cue)
    }catch(err:any){
      setCueError(err?.message || 'Failed to trigger roll')
    }finally{
      setRollingCueId(null)
    }
  }

  if(!roster.length){
    return (
      <div className="character-panel-root">
        <h3 style={{marginTop:0}}>Characters</h3>
        <div>No characters yet.</div>
        <div style={{marginTop:8}}>
          <button style={{width:'100%'}}>Add Character</button>
        </div>
      </div>
    )
  }

  return (
    <div className="character-panel-root">
      <h3 style={{marginTop:0}}>Characters</h3>
      <CharacterIconStrip character={selected} />
      <div style={{flex:1,overflowY:'auto'}} ref={containerRef}>
        <div className="character-roster">
          {roster.map(entry => (
            <div key={entry.id} className={`character-card ${entry.id === selected?.id ? 'active' : ''}`}>
              <button onClick={() => onSelect?.(entry.id)}>
                <div className="character-name">{entry.name}</div>
                <div className="character-meta">HP {entry.hp.current}/{entry.hp.max} • Level {entry.level}</div>
              </button>
            </div>
          ))}
        </div>

        <div className="character-sections">
          <div id="section-inventory" className="character-section">
            <button onClick={()=>toggle('inventory')}>Inventory</button>
            {expanded==='inventory' && (
              <div className="character-section-list">
                <ul style={{margin:0,paddingLeft:16}}>
                  {selected?.inventory.map(item => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div id="section-spells" className="character-section">
            <button onClick={()=>toggle('spells')}>Spells</button>
            {expanded==='spells' && (
              <div className="character-section-list">
                {selected?.spells.length ? (
                  <ul style={{margin:0,paddingLeft:16}}>
                    {selected.spells.map(spell => (
                      <li key={spell}>{spell}</li>
                    ))}
                  </ul>
                ) : (
                  <div>No spells prepared</div>
                )}
              </div>
            )}
          </div>

          <div id="section-skills" className="character-section">
            <button onClick={()=>toggle('skills')}>Skills</button>
            {expanded==='skills' && (
              <div className="character-section-list">
                <ul style={{margin:0,paddingLeft:16}}>
                  {selected?.skills.map(skill => (
                    <li key={skill.name}>{skill.name} {skill.mod >= 0 ? '+' : ''}{skill.mod}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
      {sceneCues.length > 0 && (
        <div style={{marginTop:12}}>
          <div style={{fontSize:12, color:'#8fe0ff', marginBottom:4}}>Scene Cues</div>
          <ul style={{margin:0, paddingLeft:16, fontSize:12, listStyle:'none'}}>
            {sceneCues.map((cue)=>(
              <li key={cue.id} style={{marginBottom:8, padding:8, borderRadius:6, border:'1px solid #1f3c4a', background:'#0b161c'}}>
                <div style={{marginBottom:6}}>{cue.prompt}</div>
                {cue.roll ? (
                  <button
                    type="button"
                    onClick={()=>handleCueRoll(cue)}
                    disabled={rollingCueId === cue.id}
                    style={{fontSize:11, padding:'4px 8px'}}
                  >
                    {rollingCueId === cue.id ? 'Rolling…' : `Roll ${cue.roll.skill || cue.roll.type || 'd20'}`}
                  </button>
                ) : (
                  <div style={{fontSize:11, color:'#999'}}>Awaiting clarification</div>
                )}
              </li>
            ))}
          </ul>
          {cueError && <div style={{fontSize:11, color:'#ff9f9f', marginTop:4}}>{cueError}</div>}
        </div>
      )}
      {npcSpotlight.length > 0 && (
        <div style={{marginTop:12}}>
          <div style={{fontSize:12, color:'#ffcc6f', marginBottom:4}}>NPC Spotlight</div>
          <ul style={{margin:0, paddingLeft:16, fontSize:12}}>
            {npcSpotlight.map(npc => (
              <li key={npc.name}>
                <strong>{npc.name}</strong>{npc.initiative_hint ? ` · ${npc.initiative_hint}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div style={{marginTop:8}}>
        <button style={{width:'100%'}}>Add Character</button>
      </div>
    </div>
  )
}
