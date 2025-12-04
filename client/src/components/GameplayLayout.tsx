import React, {useState} from 'react'
import './GameplayLayout.css'
import SiteMenu from './SiteMenu'
import NarrativeView from './NarrativeView'
import Chat from './Chat'
import CharacterPanel from './CharacterPanel'
type Props = {
  sessionId?: string | null
}

export default function GameplayLayout({sessionId}: Props){
  const [drawerOpen, setDrawerOpen] = useState(false)
  const openDrawer = () => setDrawerOpen(true)
  const closeDrawer = () => setDrawerOpen(false)

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
        <section className="scene-area" style={{flex:'1 1 60%',position:'relative',padding:'0 0 0 0'}}>
          <NarrativeView sessionId={sessionId} />
        </section>
        <div className="bottom-row" style={{display:'flex',height:'40%',minHeight:'220px'}}>
          <section className="chat-area" aria-label="Chat" style={{flex:'1 1 70%',borderTop:'1px solid #222',padding:'12px'}}><Chat sessionId={sessionId || undefined}/></section>
          <aside className="chars-area" aria-label="Character Management" style={{width:'320px',borderLeft:'1px solid #222',padding:'12px'}}><CharacterPanel/></aside>
        </div>
      </main>
    </div>
  )
}
