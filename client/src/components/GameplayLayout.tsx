import React, {useEffect, useMemo, useState} from 'react'
import './GameplayLayout.css'
import SiteMenu from './SiteMenu'
import NarrativeView from './NarrativeView'
import Chat from './Chat'
import CharacterPanel from './CharacterPanel'
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

export default function GameplayLayout({sessionId}: Props){
  const [drawerOpen, setDrawerOpen] = useState(false)
  const openDrawer = () => setDrawerOpen(true)
  const closeDrawer = () => setDrawerOpen(false)
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
        <div className="bottom-row" style={{display:'flex',height:'40%',minHeight:'220px'}}>
          <section className="chat-area" aria-label="Chat" style={{flex:'1 1 70%',borderTop:'1px solid #222',padding:'12px'}}><Chat sessionId={sessionId || undefined}/></section>
          <aside className="chars-area" aria-label="Character Management" style={{width:'320px',borderLeft:'1px solid #222',padding:'12px'}}><CharacterPanel/></aside>
        </div>
      </main>
    </div>
  )
}
