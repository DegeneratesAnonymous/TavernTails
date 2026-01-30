import React, { useCallback, useEffect, useMemo, useState } from 'react';
import '../LoggedIn.css';
import './LoggedInDashboard.css';
import GameplayLayout from './GameplayLayout'
import SessionSettings from './SessionSettings'
import { apiFetch } from '../api'
import { CharacterSummary } from './CharacterPanel'
import ImportCharacterView from './dashboard/ImportCharacterView'
import CreatingCharacterView from './dashboard/CreatingCharacterView'
import Beyond20View from './dashboard/Beyond20View'
import CampaignSetupView from './dashboard/CampaignSetupView'
import CharacterSheetModal from './characters/CharacterSheetModal'
import PageHeader from './ui/PageHeader'
import EmptyState from './ui/EmptyState'
import Modal from './ui/Modal'

type Props = {
  profile: any;
  onLogout: () => void;
};

const LoggedInDashboard: React.FC<Props> = ({ profile, onLogout }) => {
  const [view, setView] = useState<string>('gameplay');
  const [importInitialMode, setImportInitialMode] = useState<'ddb-link' | 'paste' | 'file' | 'pdf' | null>(null)
  const [campaigns, setCampaigns] = useState<Array<any>>([])
  const [activeCampaignId, setActiveCampaignId] = useState<string | null>(null)
  const [sessionMetaById, setSessionMetaById] = useState<Record<string, any>>({})
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [settingsSession, setSettingsSession] = useState<string| null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newCampaignName, setNewCampaignName] = useState('')
  const [newCampaignDescription, setNewCampaignDescription] = useState('')
  const [createCampaignBusy, setCreateCampaignBusy] = useState(false)
  const [createCampaignError, setCreateCampaignError] = useState<string | null>(null)

  const [quickstartBusy, setQuickstartBusy] = useState(false)
  const [startPlayBusy, setStartPlayBusy] = useState(false)

  const [characters, setCharacters] = useState<Array<any>>([])
  const [activeCharacterId, setActiveCharacterId] = useState<number | null>(null)
  const [newCharacterName, setNewCharacterName] = useState('')
  const [newCharacterLevel, setNewCharacterLevel] = useState<number>(1)
  const [newCharacterClass, setNewCharacterClass] = useState('')
  const [characterCreateOrigin, setCharacterCreateOrigin] = useState<'gameplay' | 'nav'>('nav')

  const [sheetModalOpen, setSheetModalOpen] = useState(false)
  const [sheetModalCharacter, setSheetModalCharacter] = useState<any | null>(null)
  const [sheetModalLoading, setSheetModalLoading] = useState(false)
  const [sheetModalError, setSheetModalError] = useState<string | null>(null)

  const activeCampaign = useMemo(() => {
    return campaigns.find(c => String(c.id) === String(activeCampaignId)) || null
  }, [activeCampaignId, campaigns])

  const activeCampaignSessions: Array<{id: string}> = useMemo(() => {
    return (activeCampaign?.sessions || [])
  }, [activeCampaign])

  const characterRoster: CharacterSummary[] = useMemo(() => {
    const toNum = (value: any): number | null => {
      const parsed = typeof value === 'number' ? value : Number(value)
      return Number.isFinite(parsed) ? parsed : null
    }

    const toStringArray = (value: any): string[] => {
      if(Array.isArray(value)) return value.map(v => String(v))
      return []
    }

    const toSkillArray = (value: any): { name: string; mod: number }[] => {
      if(!Array.isArray(value)) return []
      return value
        .map((raw: any) => {
          if(typeof raw === 'string') return { name: raw, mod: 0 }
          const name = String(raw?.name ?? '').trim()
          const mod = toNum(raw?.mod) ?? 0
          if(!name) return null
          return { name, mod }
        })
        .filter(Boolean) as any
    }

    return characters.map((c: any) => {
      const sheet = (c?.sheet && typeof c.sheet === 'object') ? c.sheet : {}
      const hpCurrent = toNum(sheet?.hp?.current ?? sheet?.hp_current) ?? 10
      const hpMax = toNum(sheet?.hp?.max ?? sheet?.hp_max) ?? Math.max(hpCurrent, 10)
      const hpTemp = toNum(sheet?.hp?.temp ?? sheet?.hp_temp) ?? 0
      const ac = toNum(sheet?.ac) ?? 10
      const spellSave = toNum(sheet?.spell_save ?? sheet?.spellSave ?? sheet?.spell_save_dc ?? sheet?.spellSaveDc) ?? 10
      const stats = (sheet?.stats && typeof sheet.stats === 'object') ? sheet.stats : {}

      const inventory = toStringArray(sheet?.inventory)
      const spells = toStringArray(sheet?.spells)
      const features = toStringArray(sheet?.features)
      const skills = toSkillArray(sheet?.skills)

      return {
        id: String(c?.id ?? ''),
        name: String(c?.name ?? 'Unnamed'),
        level: toNum(c?.level) ?? 1,
        hp: { current: hpCurrent, max: hpMax, temp: hpTemp || undefined },
        ac,
        spellSave,
        stats: {
          str: toNum(stats?.str) ?? 10,
          dex: toNum(stats?.dex) ?? 10,
          wis: toNum(stats?.wis) ?? 10,
        },
        features,
        inventoryCount: typeof sheet?.inventoryCount === 'number' ? sheet.inventoryCount : inventory.length,
        journalEntries: typeof sheet?.journalEntries === 'number' ? sheet.journalEntries : 0,
        skills,
        inventory,
        spells,
      }
    }).filter((c: any) => Boolean(c?.id))
  }, [characters])

  const fetchCampaigns = useCallback(async () => {
    try{
      const res = await apiFetch('/campaigns')
      if(res.ok){
        const data = await res.json()
        const rows = Array.isArray(data?.campaigns) ? data.campaigns : []
        setCampaigns(rows)
        if(rows.length > 0){
          setActiveCampaignId(prev => prev || String(rows[0].id))
        }
      }
    }catch(e){/*ignore*/}
  }, [])

  const fetchCharacters = useCallback(async () => {
    try{
      const res = await apiFetch('/characters')
      if(res.ok){
        const data = await res.json()
        const rows = Array.isArray(data?.characters) ? data.characters : []
        setCharacters(rows)
      }
    }catch(e){/*ignore*/}
  }, [])

  useEffect(()=>{
    fetchCampaigns()
    fetchCharacters()
  },[fetchCampaigns, fetchCharacters, profile])

  useEffect(()=>{
    if(!activeCampaignId) return
    const nextCampaign = campaigns.find(c => String(c.id) === String(activeCampaignId))
    if(!nextCampaign) return
    const sessionsList: Array<any> = nextCampaign.sessions || []
    if(sessionsList.length > 0){
      const firstId = String(sessionsList[0].id)
      // IMPORTANT: do not carry sessions across campaigns.
      // When the active campaign changes, always align activeSession to that campaign.
      setActiveSession(firstId)
    } else {
      setActiveSession(null)
    }
  },[activeCampaignId, campaigns])

  const handleSetActiveCampaignId = useCallback(async (id: string | null) => {
    setActiveCampaignId(id)
    setActiveSession(null)
    if (!id) return

    // If the campaign has no sessions yet, auto-create one so the user doesn't have to.
    const campaign = campaigns.find(c => String(c.id) === String(id))
    const sessionsList: Array<any> = (campaign?.sessions || [])
    if (sessionsList.length > 0) {
      setActiveSession(String(sessionsList[0].id))
      return
    }

    try {
      const res = await apiFetch(`/campaigns/${id}/create_session`, { method: 'POST' })
      if (!res.ok) return
      const data = await res.json().catch(() => ({} as any))
      const sid = data?.session_id ? String(data.session_id) : ''
      if (sid) {
        setActiveSession(sid)
        if (data?.meta) setSessionMetaById(prev => ({ ...prev, [sid]: data.meta }))
        await fetchCampaigns()
      }
    } catch (e) {
      // ignore; user can still create a session via checklist
    }
  }, [campaigns, fetchCampaigns])

  useEffect(()=>{
    async function ensureSessionMetas(){
      const sessionIds = activeCampaignSessions.map(s => String(s.id))
      const missing = sessionIds.filter(id => !sessionMetaById[id])
      if(missing.length === 0) return
      try{
        const results = await Promise.all(missing.map(async (id) => {
          const res = await apiFetch(`/sessions/${id}/meta`)
          if(!res.ok) return null
          const data = await res.json()
          return { id, meta: data }
        }))
        const next: Record<string, any> = { ...sessionMetaById }
        for(const item of results){
          if(item?.id){
            next[item.id] = item.meta
          }
        }
        setSessionMetaById(next)
      }catch(e){/*ignore*/}
    }
    ensureSessionMetas()
  },[activeCampaignId, activeCampaignSessions, sessionMetaById])

  useEffect(()=>{
    async function loadSessionCharacterSelection(){
      if(!activeSession) return
      try{
        const res = await apiFetch(`/sessions/${activeSession}/meta`)
        if(!res.ok) return
        const meta = await res.json()
        const email = (localStorage.getItem('user_email') || '').trim().toLowerCase()
        const username = (localStorage.getItem('user_username') || '').trim().toLowerCase()
        const identifier = email || username
        const members = Array.isArray(meta?.members) ? meta.members : []
        const me = members.find((m: any) => String(m?.email || '').trim().toLowerCase() === identifier)
        if(me && (me.character_id === null || typeof me.character_id === 'number')){
          setActiveCharacterId(me.character_id)
        }
      }catch(e){/*ignore*/}
    }
    loadSessionCharacterSelection()
  },[activeSession])

  const setSessionCharacter = useCallback(async (characterId: number | null) => {
    if(!activeSession) return
    try{
      await apiFetch(`/sessions/${activeSession}/character`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: characterId })
      })
    }catch(e){/*ignore*/}
  }, [activeSession])

  const quickstartPlaytest = useCallback(async () => {
    if (quickstartBusy) return
    setQuickstartBusy(true)
    try {
      let campaignId = activeCampaignId
      let sessionId = activeSession

      // 1) Ensure a campaign + at least one session
      if (!campaignId) {
        const label = new Date().toLocaleDateString()
        const create = await apiFetch('/campaigns', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: `Quickstart Campaign (${label})`,
            description: 'Auto-created for playtesting.',
            create_session: true,
          }),
        })
        if (!create.ok) {
          const err = await create.json().catch(() => ({} as any))
          throw new Error(err?.detail || 'Failed to create campaign')
        }
        const payload = await create.json().catch(() => ({} as any))
        const created = payload?.campaign
        campaignId = created?.id ? String(created.id) : null
        const sessions = Array.isArray(created?.sessions) ? created.sessions : []
        const firstSession = sessions[0]?.id ? String(sessions[0].id) : null
        if (campaignId) setActiveCampaignId(campaignId)
        if (firstSession) {
          sessionId = firstSession
          setActiveSession(firstSession)
        }
        await fetchCampaigns()
      }

      if (campaignId && !sessionId) {
        const res = await apiFetch(`/campaigns/${campaignId}/create_session`, { method: 'POST' })
        if (!res.ok) {
          const err = await res.json().catch(() => ({} as any))
          throw new Error(err?.detail || 'Failed to create session')
        }
        const data = await res.json().catch(() => ({} as any))
        const sid = data?.session_id ? String(data.session_id) : ''
        if (sid) {
          sessionId = sid
          setActiveSession(sid)
          if (data?.meta) setSessionMetaById(prev => ({ ...prev, [sid]: data.meta }))
          await fetchCampaigns()
        }
      }

      // 2) Ensure a character exists (demo) and is assigned to the session
      if (sessionId) {
        let myCharId: number | null = activeCharacterId
        const hasAny = characters.length > 0
        if (!hasAny) {
          const createChar = await apiFetch('/characters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: 'Arin Quickstep',
              level: 3,
              class_name: 'Rogue',
              sheet: {
                ac: 14,
                hp: { current: 22, max: 22 },
                stats: { str: 10, dex: 16, wis: 12 },
                skills: [{ name: 'Stealth', mod: 5 }, { name: 'Perception', mod: 3 }],
                inventory: ['Thieves\' tools', 'Cloak', 'Rope'],
              },
            }),
          })
          if (createChar.ok) {
            const data = await createChar.json().catch(() => ({} as any))
            const cid = data?.character?.id
            if (typeof cid === 'number') {
              myCharId = cid
              setActiveCharacterId(cid)
            }
            await fetchCharacters()
          }
        }

        if (myCharId !== null) {
          setActiveCharacterId(myCharId)
          await setSessionCharacter(myCharId)
        }

        // 3) Bootstrap an opening scene (also emits cues + suggestions now)
        const boot = await apiFetch(`/sessions/${sessionId}/bootstrap`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        })
        if (!boot.ok) {
          const err = await boot.json().catch(() => null)
          throw new Error(err?.detail || 'Failed to bootstrap scene')
        }
        const bootData = await boot.json().catch(() => ({} as any))
        if (bootData?.scene) {
          window.dispatchEvent(new CustomEvent('narrative:scene', { detail: { scene: bootData.scene } }))
        }
      }
    } catch (e: any) {
      alert(e?.message || 'Quickstart failed')
    } finally {
      setQuickstartBusy(false)
    }
  }, [
    activeCampaignId,
    activeSession,
    activeCharacterId,
    characters.length,
    fetchCampaigns,
    fetchCharacters,
    quickstartBusy,
    setSessionCharacter,
  ])

  const startPlaying = useCallback(async () => {
    if (startPlayBusy) return
    setStartPlayBusy(true)
    try {
      if (!activeCampaignId) {
        setView('gameplay')
        alert('Select or create a campaign first.')
        return
      }

      let sessionId = activeSession
      if (!sessionId) {
        const res = await apiFetch(`/campaigns/${activeCampaignId}/create_session`, { method: 'POST' })
        if (!res.ok) {
          const err = await res.json().catch(() => ({} as any))
          throw new Error(err?.detail || 'Failed to create session')
        }
        const data = await res.json().catch(() => ({} as any))
        const sid = data?.session_id ? String(data.session_id) : ''
        if (sid) {
          sessionId = sid
          setActiveSession(sid)
          if (data?.meta) setSessionMetaById(prev => ({ ...prev, [sid]: data.meta }))
          await fetchCampaigns()
        }
      }

      if (!sessionId) throw new Error('No session available')

      // Ensure we have a character selected and assigned.
      let selectedId: number | null = activeCharacterId
      if (selectedId === null && characters.length > 0) {
        const first = characters[0]
        const parsed = typeof first?.id === 'number' ? first.id : Number(first?.id)
        if (Number.isFinite(parsed)) {
          selectedId = parsed
          setActiveCharacterId(parsed)
        }
      }

      if (selectedId === null && characters.length === 0) {
        // Create a lightweight demo character for a smooth first-play loop.
        const createChar = await apiFetch('/characters', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: 'Arin Quickstep',
            level: 3,
            class_name: 'Rogue',
            sheet: {
              ac: 14,
              hp: { current: 22, max: 22 },
              stats: { str: 10, dex: 16, wis: 12 },
              skills: [{ name: 'Stealth', mod: 5 }, { name: 'Perception', mod: 3 }],
              inventory: ['Thieves\' tools', 'Cloak', 'Rope'],
            },
          }),
        })
        if (createChar.ok) {
          const data = await createChar.json().catch(() => ({} as any))
          const cid = data?.character?.id
          if (typeof cid === 'number') {
            selectedId = cid
            setActiveCharacterId(cid)
          }
          await fetchCharacters()
        }
      }

      if (selectedId !== null) {
        await setSessionCharacter(selectedId)
      }

      // Bootstrap (generates narrative scene + emits suggestions/cues)
      const boot = await apiFetch(`/sessions/${sessionId}/bootstrap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!boot.ok) {
        const err = await boot.json().catch(() => null)
        throw new Error(err?.detail || 'Failed to bootstrap scene')
      }
      const bootData = await boot.json().catch(() => ({} as any))
      if (bootData?.scene) {
        window.dispatchEvent(new CustomEvent('narrative:scene', { detail: { scene: bootData.scene } }))
      }

      setView('gameplay')
    } catch (e: any) {
      alert(e?.message || 'Failed to start playing')
    } finally {
      setStartPlayBusy(false)
    }
  }, [
    activeCampaignId,
    activeSession,
    activeCharacterId,
    characters,
    fetchCampaigns,
    fetchCharacters,
    setSessionCharacter,
    startPlayBusy,
  ])

  return (
    <div className="dashboard-root">
      {view !== 'gameplay' ? (
        <aside className="dashboard-sidebar">
          <div className="dashboard-brand">Solo TTRPG</div>
          <div className="dashboard-user">{profile?.name}</div>
          <nav className="dashboard-nav">
            <button className={`nav-btn ${view==='gameplay'?'active':''}`} onClick={() => setView('gameplay')}>Play</button>
            <button className={`nav-btn ${view==='campaign-setup'?'active':''}`} onClick={() => setView('campaign-setup')}>Manage Campaigns</button>
            <button className={`nav-btn ${view==='view-characters'?'active':''}`} onClick={() => setView('view-characters')}>Manage Characters</button>
            <button
              className={`nav-btn ${view==='import-character'?'active':''}`}
              onClick={() => {
                setImportInitialMode(null)
                setView('import-character')
              }}
            >
              Import Character
            </button>
            <button className={`nav-btn ${view==='account'?'active':''}`} onClick={() => setView('account')}>Account</button>
          </nav>
          <div className="sidebar-footer">
            <button className="btn-logout" onClick={onLogout}>Sign out</button>
          </div>
        </aside>
      ) : null}
      <main className="dashboard-main">
        {view === 'gameplay' && (
          <section className="gameplay-panel">
            <div className="gameplay-content">
              <div className="gameplay-stage">
                <GameplayLayout
                  sessionId={activeSession}
                  roster={characterRoster}
                  selectedCharId={activeCharacterId === null ? null : String(activeCharacterId)}
                  currentUserEmail={profile?.email || null}
                  currentUsername={profile?.username || profile?.name || null}
                  activeCampaignId={activeCampaignId}
                  activeCampaign={activeCampaign}
                  onCampaignUpdated={fetchCampaigns}
                  onStartCampaign={startPlaying}
                  startCampaignBusy={startPlayBusy}
                  campaigns={campaigns}
                  onSelectCampaign={handleSetActiveCampaignId}
                  onNewCampaign={() => setShowCreateModal(true)}
                  onQuickstart={quickstartPlaytest}
                  activeCharacterId={activeCharacterId}
                  onGoToCharacters={() => {
                    setCharacterCreateOrigin('gameplay')
                    setView('view-characters')
                  }}
                  onGoToImport={() => setView('import-character')}
                  onNavigate={(key) => {
                    if (key === 'gameplay') setView('gameplay')
                    if (key === 'campaign-setup') setView('campaign-setup')
                    if (key === 'view-characters') setView('view-characters')
                    if (key === 'import-character') setView('import-character')
                    if (key === 'account') setView('account')
                    if (key === 'logout') onLogout()
                  }}
                  onLogout={onLogout}
                  onSelectCharId={async (idStr) => {
                    const parsed = Number(idStr)
                    if(!Number.isFinite(parsed)) return
                    setActiveCharacterId(parsed)
                    await setSessionCharacter(parsed)
                  }}
                />
              </div>
            </div>
          </section>
        )}
        {view === 'campaign-setup' && (
          <CampaignSetupView
            activeCampaignId={activeCampaignId}
            activeCampaign={activeCampaign}
            onCampaignUpdated={fetchCampaigns}
            onCreateCampaign={() => setShowCreateModal(true)}
            onPlay={startPlaying}
            playBusy={startPlayBusy}
          />
        )}

        {view === 'view-characters' && (
          <section className="dashboard-panel stack">
            <PageHeader
              title="Characters"
              subtitle="Create or import characters. You can optionally select one for the active session to use during play."
              actions={
                <>
                  <button className="btn btn-secondary" type="button" onClick={() => setView('import-character')}>
                    Import
                  </button>
                  <button
                    className="btn"
                    type="button"
                    onClick={() => {
                      setView('creating-character')
                    }}
                  >
                    Creating a Character
                  </button>
                </>
              }
            />

            {sheetModalError && (
              <div className="inline-alert inline-alert-error">
                {sheetModalError}
              </div>
            )}

            {characters.length === 0 ? (
              <EmptyState
                title="No characters yet"
                description="Create a character from scratch, import a JSON export, or save a D&D Beyond link as a reference."
                actions={
                  <>
                    <button
                      className="btn"
                      type="button"
                      onClick={() => {
                        setView('creating-character')
                      }}
                    >
                      Creating a character
                    </button>
                    <button className="btn btn-secondary" type="button" onClick={() => setView('import-character')}>
                      Import character
                    </button>
                  </>
                }
              />
            ) : (
              <div className="card" style={{ overflow: 'hidden' }}>
                <div className="row-wrap" style={{ padding: 12, justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  <div className="muted" style={{ fontSize: 13 }}>
                    {activeSession ? `Active session: ${activeSession}` : 'No active session selected (Gameplay)'}
                  </div>
                  <div className="muted" style={{ fontSize: 13 }}>
                    {activeCharacterId !== null ? `Selected character id: ${activeCharacterId}` : 'No character selected'}
                  </div>
                </div>

                <div className="stack" style={{ gap: 0 }}>
                  {characters.map((c) => {
                    const sheet = (c?.sheet && typeof c.sheet === 'object') ? c.sheet : {}
                    const importMeta = (sheet?.import && typeof sheet.import === 'object') ? sheet.import : null
                    const source = importMeta?.source ? String(importMeta.source) : ''
                    const isSelected = activeCharacterId !== null && Number(c.id) === Number(activeCharacterId)

                    return (
                      <div
                        key={c.id}
                        className="row-wrap"
                        style={{
                          padding: 12,
                          justifyContent: 'space-between',
                          borderTop: '1px solid rgba(255,255,255,0.06)',
                          background: isSelected ? 'rgba(255,255,255,0.04)' : 'transparent',
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontWeight: 750, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {c.name}{c.class_name ? ` (${c.class_name})` : ''} — L{c.level}
                            {isSelected ? <span className="muted"> {' '}• Selected</span> : null}
                          </div>
                          <div className="muted" style={{ fontSize: 12 }}>
                            {source ? `Source: ${source}` : 'Source: manual'}
                            {importMeta?.ddb_url ? ' • DDB link stored' : ''}
                          </div>
                        </div>

                        <div className="row-wrap" style={{ justifyContent: 'flex-end' }}>
                          <button
                            className="btn btn-secondary"
                            type="button"
                            disabled={sheetModalLoading}
                            onClick={async () => {
                              setSheetModalError(null)
                              setSheetModalLoading(true)
                              setSheetModalOpen(true)
                              setSheetModalCharacter(null)
                              try {
                                const res = await apiFetch(`/characters/${c.id}`)
                                if (!res.ok) {
                                  const err = await res.json().catch(() => ({} as any))
                                  throw new Error(err?.detail || 'Failed to load character')
                                }
                                const data = await res.json()
                                setSheetModalCharacter(data?.character || null)
                              } catch (e: any) {
                                setSheetModalError(e?.message || 'Failed to load character')
                                setSheetModalOpen(false)
                              } finally {
                                setSheetModalLoading(false)
                              }
                            }}
                          >
                            View
                          </button>

                          <button
                            className="btn"
                            type="button"
                            onClick={async () => {
                              setActiveCharacterId(c.id)
                              await setSessionCharacter(c.id)
                              setView('gameplay')
                            }}
                            disabled={!activeSession}
                            aria-disabled={!activeSession}
                            style={!activeSession ? { opacity: 0.55 } : undefined}
                          >
                            Select for Session
                          </button>

                          <button
                            className="btn btn-quiet"
                            type="button"
                            onClick={async () => {
                              if (!window.confirm('Delete this character?')) return
                              const res = await apiFetch(`/characters/${c.id}`, { method: 'DELETE' })
                              if (res.ok) await fetchCharacters()
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </section>
        )}

        <CharacterSheetModal
          open={sheetModalOpen}
          character={sheetModalCharacter}
          loading={sheetModalLoading}
          onClose={() => {
            setSheetModalOpen(false)
            setSheetModalCharacter(null)
            setSheetModalLoading(false)
          }}
        />

        {view === 'create-character' && (
          <section className="dashboard-panel stack">
            <PageHeader
              title="Create Character"
              subtitle="Create a lightweight character. You can enrich it later by importing JSON."
            />
            <div style={{maxWidth:520,display:'grid',gap:10}}>
              <input className="input" placeholder="Name" value={newCharacterName} onChange={e=>setNewCharacterName(e.target.value)} />
              <input className="input" placeholder="Class (optional)" value={newCharacterClass} onChange={e=>setNewCharacterClass(e.target.value)} />
              <input className="input" type="number" min={1} max={20} value={newCharacterLevel} onChange={e=>setNewCharacterLevel(Number(e.target.value || 1))} />
              <div style={{display:'flex',gap:8}}>
                <button className="btn" onClick={async ()=>{
                  if(!newCharacterName.trim()) return alert('Enter a name')
                  const payload: any = { name: newCharacterName.trim(), level: Math.max(1, Math.min(20, Number(newCharacterLevel)||1)) }
                  if(newCharacterClass.trim()) payload.class_name = newCharacterClass.trim()
                  const res = await apiFetch('/characters', { method: 'POST', headers: { 'Content-Type':'application/json' }, body: JSON.stringify(payload) })
                  if(res.ok){
                    const data = await res.json().catch(()=>({}))
                    const createdId = typeof data?.character?.id === 'number' ? data.character.id : null
                    setNewCharacterName('')
                    setNewCharacterClass('')
                    setNewCharacterLevel(1)
                    await fetchCharacters()
                    if(activeSession && createdId !== null && characterCreateOrigin === 'gameplay'){
                      setActiveCharacterId(createdId)
                      await setSessionCharacter(createdId)
                      setView('gameplay')
                    } else {
                      if(createdId !== null) setActiveCharacterId(createdId)
                      setView('view-characters')
                    }
                  } else {
                    const err = await res.json().catch(()=>({}))
                    alert(err?.detail || 'Failed to create character')
                  }
                }}>Create</button>
                <button className="btn" onClick={()=>{
                  if(characterCreateOrigin === 'gameplay') setView('gameplay')
                  else setView('view-characters')
                }}>Cancel</button>
              </div>
            </div>
          </section>
        )}

        {view === 'creating-character' && (
          <CreatingCharacterView
            onDone={() => setView('view-characters')}
            onGoToQuickCreate={() => {
              setCharacterCreateOrigin('nav')
              setView('create-character')
            }}
            onGoToImportPdf={() => {
              setImportInitialMode('pdf')
              setView('import-character')
            }}
          />
        )}

        {view === 'import-character' && (
          <ImportCharacterView
            activeSessionId={activeSession}
            onRefreshCharacters={fetchCharacters}
            onAssignCharacterToSession={setSessionCharacter}
            onSetActiveCharacterId={setActiveCharacterId}
            initialMode={importInitialMode || undefined}
            onGoToGameplay={() => {
              setImportInitialMode(null)
              setView('gameplay')
            }}
            onDone={() => {
              setImportInitialMode(null)
              setView('view-characters')
            }}
          />
        )}

        {settingsSession && (
          <SessionSettings sessionId={settingsSession} onClose={async ()=>{ setSettingsSession(null); await fetchCampaigns() }} />
        )}

        {view === 'start-adventure' && (
          <section>
            <h2>Start New Adventure</h2>
            <p>Generate or configure a new adventure to play. (Placeholder)</p>
          </section>
        )}


        {view === 'account' && (
          <section className="dashboard-panel stack">
            <PageHeader title="Account" subtitle="Profile info for debugging; will be expanded later." />
            <pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(profile, null, 2)}</pre>

            <div className="card card-pad stack">
              <div style={{ fontWeight: 750 }}>Integrations</div>
              <div className="muted" style={{ fontSize: 13 }}>
                Beyond20 generally works from the browser extension itself (when rolling on D&amp;D Beyond or VTTs).
                This section is for optional relay/debug tooling.
              </div>
              <div className="row-wrap">
                <button className="btn btn-secondary" type="button" onClick={() => setView('beyond20')}>
                  Beyond20 settings
                </button>
              </div>
            </div>
          </section>
        )}

        {view === 'beyond20' && (
          <div className="dashboard-panel" style={{ padding: 24 }}>
            <Beyond20View activeSessionId={activeSession} />
          </div>
        )}
        <Modal
          open={showCreateModal}
          title="Create Campaign"
          onClose={() => {
            if (createCampaignBusy) return
            setShowCreateModal(false)
            setNewCampaignName('')
            setNewCampaignDescription('')
            setCreateCampaignError(null)
          }}
        >
          {createCampaignError ? (
            <div className="inline-alert inline-alert-error" style={{ marginBottom: 10 }}>
              {createCampaignError}
            </div>
          ) : null}

          <div className="stack" style={{ gap: 10 }}>
            <input
              className="input"
              placeholder="Campaign name"
              value={newCampaignName}
              onChange={(e) => setNewCampaignName(e.target.value)}
              disabled={createCampaignBusy}
            />
            <textarea
              className="input"
              placeholder="Description (optional)"
              value={newCampaignDescription}
              onChange={(e) => setNewCampaignDescription(e.target.value)}
              disabled={createCampaignBusy}
              rows={4}
            />

            <div className="row-wrap" style={{ justifyContent: 'flex-end' }}>
              <button
                className="btn"
                type="button"
                disabled={createCampaignBusy}
                onClick={async () => {
                  const name = newCampaignName.trim()
                  if (!name) {
                    setCreateCampaignError('Enter a campaign name.')
                    return
                  }

                  setCreateCampaignBusy(true)
                  setCreateCampaignError(null)
                  try {
                    const res = await apiFetch('/campaigns', {
                      method: 'POST',
                      body: JSON.stringify({
                        name,
                        description: newCampaignDescription.trim(),
                        create_session: true,
                      }),
                    })

                    if (!res.ok) {
                      const err = await res.json().catch(() => null)
                      throw new Error(err?.detail || 'Failed to create campaign')
                    }

                    const data = await res.json().catch(() => ({} as any))
                    const campaign = data?.campaign
                    if (campaign?.id) {
                      setActiveCampaignId(String(campaign.id))
                      const firstSession =
                        Array.isArray(campaign.sessions) && campaign.sessions.length > 0
                          ? String(campaign.sessions[0].id)
                          : null
                      setActiveSession(firstSession)
                    }

                    // Creating a campaign should immediately take you somewhere visible.
                    setView('campaign-setup')

                    setShowCreateModal(false)
                    setNewCampaignName('')
                    setNewCampaignDescription('')
                    await fetchCampaigns()
                  } catch (e: any) {
                    setCreateCampaignError(e?.message || 'Network error creating campaign')
                  } finally {
                    setCreateCampaignBusy(false)
                  }
                }}
              >
                {createCampaignBusy ? 'Creating…' : 'Create'}
              </button>
              <button
                className="btn btn-secondary"
                type="button"
                disabled={createCampaignBusy}
                onClick={() => {
                  setShowCreateModal(false)
                  setNewCampaignName('')
                  setNewCampaignDescription('')
                  setCreateCampaignError(null)
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </Modal>
      </main>
    </div>
  );
};

export default LoggedInDashboard;
