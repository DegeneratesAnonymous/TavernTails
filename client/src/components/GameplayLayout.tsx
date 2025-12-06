import React, {useEffect, useMemo, useState} from 'react'
import './GameplayLayout.css'
import SiteMenu from './SiteMenu'
import NarrativeView from './NarrativeView'
import Chat from './Chat'
import CharacterPanel, {CharacterSummary} from './CharacterPanel'
import PlayerStatusBar from './PlayerStatusBar'
type Props = {
  sessionId?: string | null
}

type Banner = {
  id: string
  title: string
  subtitle?: string
}

const defaultSuggestions = [
  'Survey the immediate area',
  'Address the NPC who spoke',
  'Ready an action or spell',
]

const demoRoster: CharacterSummary[] = [
  {
    id: 'aria',
    name: 'Aria the Ranger',
    level: 3,
    hp: { current: 18, max: 18, temp: 3 },
    ac: 15,
    spellSave: 14,
    stats: { str: 12, dex: 16, wis: 14 },
    features: ["Hunter's Quarry", 'Primeval Awareness', 'Favored Foe'],
    inventoryCount: 9,
    journalEntries: 5,
    skills: [
      { name: 'Perception', mod: 5 },
      { name: 'Stealth', mod: 4 },
    ],
    inventory: ['Rope', 'Lantern', 'Travel Cloak', 'Healing Potion'],
    spells: ['Hunter\'s Mark', 'Cure Wounds'],
  },
  {
    id: 'torin',
    name: 'Torin the Fighter',
    level: 4,
    hp: { current: 32, max: 32 },
    ac: 18,
    spellSave: 0,
    stats: { str: 17, dex: 13, wis: 11 },
    features: ['Second Wind', 'Action Surge'],
    inventoryCount: 6,
    journalEntries: 3,
    skills: [
      { name: 'Athletics', mod: 7 },
      { name: 'Intimidation', mod: 4 },
    ],
    inventory: ['Greatsword', 'Shield', 'Traveler\'s Clothes'],
    spells: [],
  },
]

export default function GameplayLayout({sessionId}: Props){
  const [drawerOpen, setDrawerOpen] = useState(false)
  const openDrawer = () => setDrawerOpen(true)
  const closeDrawer = () => setDrawerOpen(false)
  const [selectedCharId, setSelectedCharId] = useState<string | null>(demoRoster[0]?.id ?? null)
  const [campaignTitle, setCampaignTitle] = useState('Current Campaign')
  const [waitingOn, setWaitingOn] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])

  useEffect(()=>{
    const handler = (event: Event)=>{
      const detail = (event as CustomEvent).detail
      if(detail?.title){
        setCampaignTitle(detail.title)
      }
    }
    // @ts-ignore
    window.addEventListener('session:campaign', handler)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('session:campaign', handler)
    }
  },[])

  useEffect(()=>{
    const handler = (event: Event)=>{
      const detail = (event as CustomEvent).detail
      setWaitingOn(detail?.player ?? null)
    }
    // @ts-ignore
    window.addEventListener('session:waiting', handler)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('session:waiting', handler)
    }
  },[])

  useEffect(()=>{
    const handler = (event: Event)=>{
      const detail = (event as CustomEvent).detail
      if(Array.isArray(detail?.suggestions)){
        setSuggestions(detail.suggestions)
      }
    }
    // @ts-ignore
    window.addEventListener('narrative:suggestions', handler)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('narrative:suggestions', handler)
    }
  },[])

  const banners: Banner[] = useMemo(()=>{
    const entries: Banner[] = [
      {id:'title', title: campaignTitle, subtitle: sessionId ? `Session ${sessionId}` : 'Session overview'},
    ]
    if(waitingOn){
      entries.push({id:'waiting', title: `Waiting on ${waitingOn}`, subtitle: 'Ready when they are'})
    }
    return entries
  }, [campaignTitle, waitingOn, sessionId])

  const [bannerIndex, setBannerIndex] = useState(0)
  useEffect(()=>{
    if(!banners.length) return
    const id = window.setInterval(()=>{
      setBannerIndex((i)=> (i + 1) % banners.length)
    }, 6000)
    return ()=>window.clearInterval(id)
  }, [banners.length])
  const activeBanner = banners[bannerIndex % (banners.length || 1)]
  const visibleSuggestions = suggestions.length ? suggestions : defaultSuggestions
  const selectedCharacter = useMemo(() => {
    if(!demoRoster.length) return undefined
    if(!selectedCharId) return demoRoster[0]
    return demoRoster.find(c => c.id === selectedCharId) ?? demoRoster[0]
  }, [selectedCharId])

  const playerStats = selectedCharacter ?? demoRoster[0]

  return (
    <div className="gameplay-root" style={{height:'100%', minHeight:0, display:'flex', background:'#18181a'}}>
      <button className="drawer-toggle" aria-label="Open command drawer" aria-expanded={drawerOpen} onClick={openDrawer}>
        Menu
      </button>
      <div className={`drawer-scrim ${drawerOpen ? 'visible' : ''}`} onClick={closeDrawer} aria-hidden={!drawerOpen} />
      <aside className={`command-drawer ${drawerOpen ? 'open' : ''}`} aria-label="Command drawer">
        <SiteMenu onClose={closeDrawer} />
      </aside>
      <main className="gameplay-main" style={{flex:1,display:'flex',flexDirection:'column'}}>
        <section className="session-banner" aria-live="polite">
          <div className="session-banner-title">{activeBanner?.title}</div>
          {activeBanner?.subtitle && <div className="session-banner-subtitle">{activeBanner.subtitle}</div>}
        </section>
        <section className="scene-area" style={{flex:'1 1 60%',position:'relative',padding:'0 0 0 0'}}>
          <NarrativeView sessionId={sessionId} />
        </section>
        <section className="suggestions-bar" aria-label="Agent suggestions">
          <span className="suggestions-label">Suggestions</span>
          <div className="suggestions-list">
            {visibleSuggestions.map((text, idx)=>(
              <button key={`${text}-${idx}`} className="suggestion-pill" type="button">
                {text}
              </button>
            ))}
          </div>
        </section>
        {playerStats && (
          <PlayerStatusBar
            name={playerStats.name}
            ac={playerStats.ac}
            hp={{ current: playerStats.hp.current, max: playerStats.hp.max }}
            tempHp={playerStats.hp.temp || 0}
            deathSaves={{ success: 1, failure: 0 }}
            exhaustion={0}
            spellSaveDc={playerStats.spellSave || 10}
          />
        )}
        <div className="bottom-row" style={{display:'flex',height:'40%',minHeight:'220px'}}>
          <section className="chat-area" aria-label="Chat" style={{flex:'1 1 70%',borderTop:'1px solid #222',padding:'12px'}}><Chat sessionId={sessionId || undefined}/></section>
          <aside className="chars-area" aria-label="Character Management" style={{width:'320px',borderLeft:'1px solid #222',padding:'12px'}}>
            <CharacterPanel roster={demoRoster} selectedId={playerStats?.id} onSelect={setSelectedCharId} />
          </aside>
        </div>
      </main>
    </div>
  )
}
