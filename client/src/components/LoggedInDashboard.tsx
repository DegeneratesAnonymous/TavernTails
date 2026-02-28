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
import DashboardHome from './dashboard/DashboardHome'
import AdminPanel from './dashboard/AdminPanel'
import CharacterSheetModal from './characters/CharacterSheetModal'
import ContactModal from './ui/ContactModal'
import BlockReportModal from './ui/BlockReportModal'
import InboxPanel from './dashboard/InboxPanel'
import MyTicketsPanel from './dashboard/MyTicketsPanel'
import PageHeader from './ui/PageHeader'
import EmptyState from './ui/EmptyState'
import Modal from './ui/Modal'

// Container category names that should not appear as individual features
const FEATURE_CATEGORY_PATTERN = /\b(features|abilities|traits|proficiencies)\s*$/i
const FEATURE_SKIP_NAMES = new Set(['proficiencies', 'features', 'traits', 'abilities', 'other proficiencies & languages', 'other proficiencies and languages'])

type Props = {
  profile: any;
  onLogout: () => void;
};

type NotificationItem = {
  id: string
  title: string
  body?: string
  createdAt?: string | null
  read?: boolean
  type?: 'friend_invite' | 'campaign_invite' | 'general'
  actionData?: Record<string, any>
}

const LoggedInDashboard: React.FC<Props> = ({ profile, onLogout }) => {
  const [view, setView] = useState<string>('home');
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [contactModalOpen, setContactModalOpen] = useState(false)
  const [blockReportModalOpen, setBlockReportModalOpen] = useState(false)
  const [blockReportTarget, setBlockReportTarget] = useState<{ id: number; name: string } | null>(null)
  const [blockReportMode, setBlockReportMode] = useState<'block' | 'report'>('report')
  const [moderationSearchQuery, setModerationSearchQuery] = useState('')
  const [moderationSearchResults, setModerationSearchResults] = useState<Array<any>>([])
  const [moderationSearchBusy, setModerationSearchBusy] = useState(false)
  const [importInitialMode, setImportInitialMode] = useState<'pdf' | 'beyond20' | null>(null)
  const [campaigns, setCampaigns] = useState<Array<any>>([])
  const [activeCampaignId, setActiveCampaignId] = useState<string | null>(null)
  const [sessionMetaById, setSessionMetaById] = useState<Record<string, any>>({})
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [settingsSession, setSettingsSession] = useState<string| null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createCampaignBusy, setCreateCampaignBusy] = useState(false)
  const [createCampaignError, setCreateCampaignError] = useState<string | null>(null)
  const [newCampaignName, setNewCampaignName] = useState('')
  const [newCampaignDescription, setNewCampaignDescription] = useState('')
  const [newCampaignGenre, setNewCampaignGenre] = useState('fantasy')
  const [newCampaignTone, setNewCampaignTone] = useState('balanced')
  const [newCampaignPacing, setNewCampaignPacing] = useState('moderate')
  const [newCampaignContentRating, setNewCampaignContentRating] = useState('pg-13')

  const [quickstartBusy, setQuickstartBusy] = useState(false)
  const [startPlayBusy, setStartPlayBusy] = useState(false)

  const [showQuickstartSetup, setShowQuickstartSetup] = useState(false)
  const [quickstartCampaignName, setQuickstartCampaignName] = useState('')
  const [quickstartCampaignNameError, setQuickstartCampaignNameError] = useState<string | null>(null)
  const [quickstartSelectedCharId, setQuickstartSelectedCharId] = useState<string>('__none__')

  const [characters, setCharacters] = useState<Array<any>>([])
  const [activeCharacterId, setActiveCharacterId] = useState<number | null>(null)
  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(null)
  const [newCharacterName, setNewCharacterName] = useState('')
  const [newCharacterLevel, setNewCharacterLevel] = useState<number>(1)
  const [newCharacterClass, setNewCharacterClass] = useState('')
  const [characterCreateOrigin, setCharacterCreateOrigin] = useState<'gameplay' | 'nav'>('nav')

  const [sheetModalOpen, setSheetModalOpen] = useState(false)
  const [sheetModalCharacter, setSheetModalCharacter] = useState<any | null>(null)
  const [sheetModalLoading, setSheetModalLoading] = useState(false)
  const [characterSettingsOpen, setCharacterSettingsOpen] = useState(false)
  const [characterPanelMode, setCharacterPanelMode] = useState<'summary' | 'spells' | 'features' | 'journal' | 'inventory'>('summary')
  const [selectedSpellRow, setSelectedSpellRow] = useState<any | null>(null)
  const [showAllFeatures, setShowAllFeatures] = useState(false)
  const [selectedFeatureRow, setSelectedFeatureRow] = useState<any | null>(null)
  const [showAllSummaryInventory, setShowAllSummaryInventory] = useState(false)
  const [showAllSummarySkills, setShowAllSummarySkills] = useState(false)
  const [showAllInventoryPanel, setShowAllInventoryPanel] = useState(false)

  const SettingsIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
      <path strokeLinecap="round" strokeLinejoin="round" d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 0 1 1.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.559.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.894.149c-.424.07-.764.383-.929.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 0 1-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.398.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 0 1-.12-1.45l.527-.737c.25-.35.272-.806.108-1.204-.165-.397-.506-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.765-.383.93-.78.165-.398.143-.854-.108-1.204l-.526-.738a1.125 1.125 0 0 1 .12-1.45l.773-.773a1.125 1.125 0 0 1 1.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
    </svg>
  )

  const DeleteIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="btn-icon">
      <path strokeLinecap="round" strokeLinejoin="round" d="m9.75 9.75 4.5 4.5m0-4.5-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  )

  const [npcModalOpen, setNpcModalOpen] = useState(false)
  const [npcModalBusy, setNpcModalBusy] = useState(false)
  const [npcModalError, setNpcModalError] = useState<string | null>(null)
  const [npcModalItems, setNpcModalItems] = useState<Array<any>>([])
  const [npcModalCharacter, setNpcModalCharacter] = useState<any | null>(null)
  const [npcModalCampaignId, setNpcModalCampaignId] = useState<string | null>(null)
  const [npcCampaignPickId, setNpcCampaignPickId] = useState<string | null>(null)
  const [npcRememberCampaign, setNpcRememberCampaign] = useState(true)

  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [readNotificationIds, setReadNotificationIds] = useState<string[]>([])
  const [pendingFriendRequests, setPendingFriendRequests] = useState<Array<any>>([])
  const [accountSection, setAccountSection] = useState<'profile' | 'invites' | null>(null)
  const [accountTab, setAccountTab] = useState<'profile' | 'inbox' | 'tickets'>('profile')
  const [accountEditName, setAccountEditName] = useState<string | null>(null)
  const [accountEditEmail, setAccountEditEmail] = useState<string | null>(null)
  const [accountEditUsername, setAccountEditUsername] = useState<string | null>(null)
  const [accountSaving, setAccountSaving] = useState(false)
  const [accountSaveMsg, setAccountSaveMsg] = useState<{ kind: 'info' | 'error'; text: string } | null>(null)
  const [accountEditMode, setAccountEditMode] = useState(false)
  const [changePwOpen, setChangePwOpen] = useState(false)
  const [changePwCurrent, setChangePwCurrent] = useState('')
  const [changePwNew, setChangePwNew] = useState('')
  const [changePwConfirm, setChangePwConfirm] = useState('')
  const [changePwBusy, setChangePwBusy] = useState(false)
  const [changePwMsg, setChangePwMsg] = useState<{ kind: 'info' | 'error'; text: string } | null>(null)
  const invitesCardRef = React.useRef<HTMLDivElement | null>(null)

  // Scroll to invites card when navigated from a notification
  React.useEffect(() => {
    if (accountSection === 'invites' && invitesCardRef.current) {
      invitesCardRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setAccountSection(null)
    }
  }, [accountSection, view])

  const notifications: NotificationItem[] = useMemo(() => {
    const raw = Array.isArray(profile?.notifications) ? profile.notifications : []
    const profileNotifs: NotificationItem[] = raw.map((item: any, idx: number) => {
      const id = String(item?.id ?? item?.notification_id ?? `notification-${idx}`)
      return {
        id,
        title: String(item?.title ?? item?.message ?? item?.text ?? 'Notification'),
        body: item?.body ? String(item.body) : (item?.detail ? String(item.detail) : undefined),
        createdAt: item?.created_at || item?.createdAt || item?.timestamp || null,
        read: Boolean(item?.read),
        type: (item?.type as NotificationItem['type']) || 'general',
        actionData: item?.action_data || undefined,
      }
    })
    // Synthetic notifications for pending friend requests
    const friendNotifs: NotificationItem[] = pendingFriendRequests.map((req: any) => {
      const fromProfile = req?.from_profile || {}
      const fromName = fromProfile?.name || fromProfile?.username || fromProfile?.email || `User ${req?.from_id}`
      return {
        id: `friend-invite-${req?.from_id}`,
        title: `Friend request from ${fromName}`,
        body: 'Tap to view and accept.',
        createdAt: null,
        read: readNotificationIds.includes(`friend-invite-${req?.from_id}`),
        type: 'friend_invite' as const,
        actionData: { from_id: req?.from_id, from_profile: fromProfile },
      }
    })
    return [...profileNotifs, ...friendNotifs]
  }, [profile?.notifications, pendingFriendRequests, readNotificationIds])

  const sortedNotifications = useMemo(() => {
    return [...notifications].sort((a, b) => {
      const at = a.createdAt ? new Date(a.createdAt).getTime() : 0
      const bt = b.createdAt ? new Date(b.createdAt).getTime() : 0
      if (at && bt && at !== bt) return bt - at
      return b.id.localeCompare(a.id)
    })
  }, [notifications])

  const isNotificationRead = (item: NotificationItem) => {
    return Boolean(item.read) || readNotificationIds.includes(item.id)
  }

  const unreadCount = sortedNotifications.filter((item) => !isNotificationRead(item)).length

  const isAdmin = useMemo(() => {
    const roles = Array.isArray(profile?.roles) ? profile.roles : []
    return Boolean(profile?.admin) || roles.some((r: any) => String(r).toLowerCase() === 'admin')
  }, [profile?.admin, profile?.roles])

  const [adminMode, setAdminMode] = useState<boolean>(() => {
    const pref = profile?.preferences && typeof profile.preferences === 'object' ? profile.preferences : {}
    if (typeof pref?.admin_mode === 'boolean') return pref.admin_mode
    return Boolean(profile?.admin)
  })

  useEffect(() => {
    const pref = profile?.preferences && typeof profile.preferences === 'object' ? profile.preferences : {}
    if (typeof pref?.admin_mode === 'boolean') {
      setAdminMode(pref.admin_mode)
      return
    }
    setAdminMode(Boolean(profile?.admin))
  }, [profile?.preferences, profile?.admin])

  const handleToggleAdminMode = useCallback(async (enabled: boolean) => {
    try {
      const res = await apiFetch('/player/admin-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => null)
        const message = detail?.detail || detail?.message || `Unable to update admin mode (${res.status}).`
        alert(message)
        return
      }
      setAdminMode(enabled)
    } catch {
      alert('Network error while updating admin mode.')
    }
  }, [])

  const handleMarkAllRead = () => {
    setReadNotificationIds(sortedNotifications.map((n) => n.id))
  }

  const activeCampaign = useMemo(() => {
    return campaigns.find(c => String(c.id) === String(activeCampaignId)) || null
  }, [activeCampaignId, campaigns])

  const playerRunMode = useMemo(() => {
    const settings = (activeCampaign as any)?.metadata_json?.settings
    return Boolean(settings?.player_run_mode)
  }, [activeCampaign])

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
          const mod = toNum(raw?.mod ?? raw?.modifier) ?? 0
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
      const spellbook = Array.isArray(sheet?.spellbook) ? sheet.spellbook : []
      const features = toStringArray(sheet?.features)
      const skills = toSkillArray(sheet?.skills)
      const exhaustion = typeof sheet?.exhaustion === 'number' ? sheet.exhaustion : 0
      const rawDs = sheet?.death_saves ?? sheet?.deathSaves
      const deathSaves = rawDs && typeof rawDs === 'object'
        ? { successes: toNum(rawDs.successes) ?? 0, failures: toNum(rawDs.failures) ?? 0 }
        : { successes: 0, failures: 0 }
      const spellSlots = (sheet?.spell_slots && typeof sheet.spell_slots === 'object') ? sheet.spell_slots : undefined

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
        spellbook,
        exhaustion,
        deathSaves,
        spellSlots,
      }
    }).filter((c: any) => Boolean(c?.id))
  }, [characters])

  const formatModifier = (value: number | null | undefined) => {
    if (value === null || value === undefined || Number.isNaN(value)) return '—'
    return value >= 0 ? `+${value}` : String(value)
  }

  const selectedCharacter = useMemo(() => {
    if (selectedCharacterId === null) return null
    return characters.find((c) => Number(c?.id) === Number(selectedCharacterId)) || null
  }, [characters, selectedCharacterId])

  useEffect(() => {
    if (!selectedCharacter) {
      setCharacterPanelMode('summary')
      setSelectedSpellRow(null)
      setSelectedFeatureRow(null)
      setShowAllFeatures(false)
      setShowAllSummaryInventory(false)
      setShowAllSummarySkills(false)
      setShowAllInventoryPanel(false)
    }
  }, [selectedCharacter])

  const selectedSheetSummary = useMemo(() => {
    if (!selectedCharacter) return null
    const sheet = (selectedCharacter?.sheet && typeof selectedCharacter.sheet === 'object') ? selectedCharacter.sheet : {}
    const stats = (sheet?.stats && typeof sheet.stats === 'object') ? sheet.stats : {}
    const hpCurrent = typeof sheet?.hp?.current === 'number' ? sheet.hp.current : (typeof sheet?.hp_current === 'number' ? sheet.hp_current : null)
    const hpMax = typeof sheet?.hp?.max === 'number' ? sheet.hp.max : (typeof sheet?.hp_max === 'number' ? sheet.hp_max : null)
    const hpTemp = typeof sheet?.hp?.temp === 'number' ? sheet.hp.temp : (typeof sheet?.hp_temp === 'number' ? sheet.hp_temp : null)
    const ac = typeof sheet?.ac === 'number' ? sheet.ac : null
    const speed = (sheet?.speed && typeof sheet.speed === 'object') ? sheet.speed : null

    const statValue = (key: keyof typeof stats) => {
      const value = (stats as any)?.[key]
      return typeof value === 'number' ? value : null
    }

    const modValue = (score: number | null) => (typeof score === 'number' ? Math.floor((score - 10) / 2) : null)

    const toList = (value: any): string[] => {
      if (!Array.isArray(value)) return []
      return value.map((v) => String(v)).map((v) => v.trim()).filter(Boolean)
    }

    const toFeatureList = (value: any): Array<{ name: string; source?: string; description?: string }> => {
      if (!Array.isArray(value)) return []
      return value
        .map((v) => {
          if (typeof v === 'string') {
            const name = v.trim()
            if (!name) return null
            const lower = name.toLowerCase()
            // Skip bare container category names with no real feature info
            if (FEATURE_SKIP_NAMES.has(lower)) return null
            if (FEATURE_CATEGORY_PATTERN.test(name) && !name.includes(':')) return null
            return { name }
          }
          if (v && typeof v === 'object') {
            const name = String(v.name || '').trim()
            if (!name) return null
            const lower = name.toLowerCase()
            const desc = v.description ? String(v.description) : undefined
            if (FEATURE_SKIP_NAMES.has(lower)) return null
            // Filter container category names only when they have no description
            if (!desc && FEATURE_CATEGORY_PATTERN.test(name) && !name.includes(':')) return null
            return { name, source: v.source ? String(v.source) : undefined, description: desc }
          }
          return null
        })
        .filter(Boolean) as Array<{ name: string; source?: string; description?: string }>
    }

    const uniq = (items: string[]) => Array.from(new Set(items))
    const uniqFeatures = (items: Array<{ name: string; source?: string; description?: string }>) => {
      const seen = new Set<string>()
      return items.filter((f) => {
        const key = `${f.name}|${f.source || ''}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
    }
    const summarize = (items: string[], limit = 8) => ({
      items: items.slice(0, limit),
      all: items,
      more: Math.max(0, items.length - limit),
    })
    const summarizeFeatures = (items: Array<{ name: string; source?: string; description?: string }>) => ({
      items,
      more: 0,
    })

    const classFeatures = uniqFeatures(toFeatureList((sheet as any)?.classFeatures))
    const racialFeatures = uniqFeatures(toFeatureList((sheet as any)?.racialFeatures))
    const otherFeaturesSrc = uniqFeatures([
      ...toFeatureList((sheet as any)?.otherFeatures),
      ...toFeatureList(sheet?.features),
    ])
    // Deduplicate: remove items already in class/racial by name+source composite key
    const classOrRaceKeys = new Set([
      ...classFeatures.map(f => `${f.name}::${f.source || ''}`),
      ...racialFeatures.map(f => `${f.name}::${f.source || ''}`),
    ])
    const otherFeatures = otherFeaturesSrc.filter(f => !classOrRaceKeys.has(`${f.name}::${f.source || ''}`))

    // Group class features by source (class name) if source info is available
    const classFeatureGroups: Array<{ label: string; items: Array<{ name: string; source?: string; description?: string }> }> = []
    const classFeaturesBySource = new Map<string, Array<{ name: string; source?: string; description?: string }>>()
    for (const f of classFeatures) {
      const src = f.source || 'Class Features'
      if (!classFeaturesBySource.has(src)) classFeaturesBySource.set(src, [])
      classFeaturesBySource.get(src)!.push(f)
    }
    if (classFeaturesBySource.size > 1) {
      classFeaturesBySource.forEach((items, label) => classFeatureGroups.push({ label, items }))
    } else if (classFeatures.length) {
      classFeatureGroups.push({ label: 'Class Features', items: classFeatures })
    }

    const featureGroups: Array<{ label: string; items: Array<{ name: string; source?: string; description?: string }> }> = [
      ...classFeatureGroups,
      ...(racialFeatures.length ? [{ label: 'Racial / Species Features', items: racialFeatures }] : []),
      ...(otherFeatures.length ? [{ label: 'Other Features', items: otherFeatures }] : []),
    ]
    const allFeaturesFlat = uniqFeatures([...classFeatures, ...racialFeatures, ...otherFeatures])

    const spells = uniq(toList(sheet?.spells))
    // inventory: prefer string list, fallback to equipment objects
    const inventoryRaw = Array.isArray(sheet?.inventory) && sheet.inventory.length > 0
      ? sheet.inventory
      : Array.isArray(sheet?.equipment) ? sheet.equipment : []
    const inventory = uniq(
      inventoryRaw.map((item: any) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object') {
          const name = String(item?.name ?? item?.definition?.name ?? '').trim()
          return name || null
        }
        return null
      }).filter(Boolean) as string[]
    )
    // Handle skills as either strings or objects {name, mod, modifier, proficient}
    const skillsRaw = Array.isArray(sheet?.skills) ? sheet.skills : []
    const skills = uniq(
      skillsRaw.map((s: any) => {
        if (typeof s === 'string') return s
        const name = String(s?.name ?? '').trim()
        if (!name) return null
        const mod = typeof s?.mod === 'number' ? s.mod : (typeof s?.modifier === 'number' ? s.modifier : null)
        return mod !== null ? `${name} (${mod >= 0 ? '+' : ''}${mod})` : name
      }).filter(Boolean) as string[]
    )

    const dexScore = statValue('dex')
    const wisScore = statValue('wis')

    // Proficiencies
    const proficienciesSkilled = skillsRaw
      .filter((s: any) => s && typeof s === 'object' && s.proficient === true)
      .map((s: any) => String(s.name || '').trim())
      .filter(Boolean)
    const languages = uniq(toList(sheet?.languages))
    const armorProf = uniq(toList(sheet?.armor_proficiencies))
    const weaponProf = uniq(toList(sheet?.weapon_proficiencies))
    const toolProf = uniq(toList(sheet?.tool_proficiencies))
    const otherProf = uniq(toList(sheet?.other_proficiencies))

    return {
      stats,
      statScores: {
        str: statValue('str'),
        dex: dexScore,
        con: statValue('con'),
        int: statValue('int'),
        wis: wisScore,
        cha: statValue('cha'),
      },
      statMods: {
        str: modValue(statValue('str')),
        dex: modValue(dexScore),
        con: modValue(statValue('con')),
        int: modValue(statValue('int')),
        wis: modValue(wisScore),
        cha: modValue(statValue('cha')),
      },
      initiative: modValue(dexScore),
      passivePerception: typeof wisScore === 'number' ? 10 + (modValue(wisScore) ?? 0) : null,
      speed,
      hpCurrent,
      hpMax,
      hpTemp,
      ac,
      features: summarizeFeatures(allFeaturesFlat),
      featureGroups,
      spells: summarize(spells, 10),
      inventory: summarize(inventory, 8),
      skills: summarize(skills, 8),
      proficiencies: {
        skilled: proficienciesSkilled,
        languages,
        armor: armorProf,
        weapons: weaponProf,
        tools: toolProf,
        other: otherProf,
      },
    }
  }, [selectedCharacter])

  useEffect(() => {
    if (!selectedCharacter || characterPanelMode !== 'spells') return
    if (selectedSpellRow) return
    const sheet = (selectedCharacter?.sheet && typeof selectedCharacter.sheet === 'object') ? selectedCharacter.sheet : {}
    const spellbook = Array.isArray((sheet as any)?.spellbook) ? (sheet as any).spellbook : []
    const spellNames = Array.isArray((sheet as any)?.spells) ? (sheet as any).spells : []
    if (spellbook.length > 0) {
      setSelectedSpellRow(spellbook[0])
    } else if (spellNames.length > 0) {
      setSelectedSpellRow({ name: String(spellNames[0]) })
    }
  }, [characterPanelMode, selectedCharacter, selectedSpellRow])

  useEffect(() => {
    if (!characters.length) {
      setSelectedCharacterId(null)
      return
    }
    const hasSelected = selectedCharacterId !== null && characters.some((c) => Number(c?.id) === Number(selectedCharacterId))
    if (hasSelected) return
    if (activeCharacterId !== null && characters.some((c) => Number(c?.id) === Number(activeCharacterId))) {
      setSelectedCharacterId(activeCharacterId)
      return
    }
    setSelectedCharacterId(Number(characters[0].id))
  }, [characters, activeCharacterId, selectedCharacterId])

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

  const fetchPendingFriends = useCallback(async () => {
    try {
      const res = await apiFetch('/player/friends')
      if (res.ok) {
        const data = await res.json()
        const pending = Array.isArray(data?.pending) ? data.pending : []
        setPendingFriendRequests(pending)
      }
    } catch (e) { /* ignore */ }
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

  const updateCharacterCampaignAssociation = useCallback(async (characterId: number, campaignId: string | null) => {
    if (!characterId || !campaignId) return
    try {
      const existing = characters.find((c) => Number(c?.id) === Number(characterId)) || null
      let sheet = (existing?.sheet && typeof existing.sheet === 'object') ? existing.sheet : null
      if (!sheet) {
        const res = await apiFetch(`/characters/${characterId}`)
        if (res.ok) {
          const data = await res.json().catch(() => ({} as any))
          sheet = (data?.character?.sheet && typeof data.character.sheet === 'object') ? data.character.sheet : {}
        } else {
          sheet = {}
        }
      }
      const assoc = (sheet && typeof sheet === 'object') ? (sheet as any).associations : null
      const nextSheet = {
        ...(sheet || {}),
        associations: {
          ...(assoc && typeof assoc === 'object' ? assoc : {}),
          campaign_id: campaignId,
        },
      }
      const res = await apiFetch(`/characters/${characterId}`, {
        method: 'PUT',
        body: JSON.stringify({ sheet: nextSheet }),
      })
      if (res.ok) await fetchCharacters()
    } catch {
      // ignore; association is best-effort
    }
  }, [characters, fetchCharacters])

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

  const assignCharacterToSession = useCallback(async (characterId: number | null) => {
    await setSessionCharacter(characterId)
    if (characterId !== null && activeCampaignId) {
      await updateCharacterCampaignAssociation(characterId, activeCampaignId)
    }
  }, [activeCampaignId, setSessionCharacter, updateCharacterCampaignAssociation])

  const handleDeleteTestCampaigns = useCallback(async () => {
    const confirmDelete = window.confirm('Delete test campaigns (name contains "test")? This cannot be undone.')
    if (!confirmDelete) return
    try {
      const res = await apiFetch('/campaigns/purge?name_like=test', { method: 'DELETE' })
      if (!res.ok) {
        const detail = await res.json().catch(() => null)
        const message = detail?.detail || detail?.message || `Delete failed (${res.status}).`
        alert(message)
        return
      }
      await fetchCampaigns()
      alert('Deleted test campaigns.')
    } catch {
      alert('Network error. Please try again.')
    }
  }, [fetchCampaigns])

  const loadNpcList = useCallback(async (campaignId: string, character: any, rememberAssociation: boolean) => {
    setNpcModalBusy(true)
    setNpcModalError(null)
    try {
      const campaign = campaigns.find((c) => String(c.id) === String(campaignId))
      if (!campaign) {
        setNpcModalError('Campaign not found.')
        setNpcModalItems([])
        return
      }
      const sessions = Array.isArray(campaign.sessions) ? campaign.sessions : []
      if (!sessions.length) {
        setNpcModalItems([])
        setNpcModalCampaignId(String(campaignId))
        return
      }

      const npcBuckets = await Promise.all(
        sessions.map(async (s: any) => {
          const sid = String(s?.id || '')
          if (!sid) return []
          try {
            const res = await apiFetch(`/sessions/${sid}/party`)
            if (!res.ok) return []
            const data = await res.json().catch(() => null)
            const npcs = Array.isArray(data?.npcs) ? data.npcs : []
            return npcs.map((npc: any) => ({ ...npc, session_id: sid }))
          } catch {
            return []
          }
        })
      )

      const flat = npcBuckets.flat()
      const deduped = new Map<string, any>()
      for (const npc of flat) {
        const name = String(npc?.name || '').trim()
        if (!name) continue
        if (!deduped.has(name)) {
          deduped.set(name, npc)
        }
      }
      const visible = Array.from(deduped.values()).map((npc) => ({
        name: String(npc?.name || 'Unknown NPC'),
        traits: npc?.traits || {},
        motivations: Array.isArray(npc?.motivations) ? npc.motivations : [],
        quirks: Array.isArray(npc?.quirks) ? npc.quirks : [],
        session_id: npc?.session_id,
      })).sort((a, b) => a.name.localeCompare(b.name))

      setNpcModalItems(visible)
      setNpcModalCampaignId(String(campaignId))

      if (rememberAssociation && character?.id) {
        await updateCharacterCampaignAssociation(Number(character.id), String(campaignId))
      }
    } catch (e: any) {
      setNpcModalError(e?.message || 'Failed to load NPCs.')
    } finally {
      setNpcModalBusy(false)
    }
  }, [campaigns, updateCharacterCampaignAssociation])

  const openNpcModalForCharacter = useCallback((character: any) => {
    const sheet = (character?.sheet && typeof character.sheet === 'object') ? character.sheet : {}
    const assocCampaignId = sheet?.associations?.campaign_id || sheet?.campaign_id || null
    const defaultCampaignId = assocCampaignId || activeCampaignId || (campaigns[0]?.id ? String(campaigns[0].id) : null)
    const shouldPrompt = Boolean(
      (assocCampaignId && activeCampaignId && String(assocCampaignId) !== String(activeCampaignId)) ||
      (!assocCampaignId && campaigns.length > 1)
    )

    setNpcModalCharacter(character)
    setNpcModalItems([])
    setNpcModalError(null)
    setNpcModalCampaignId(null)
    setNpcCampaignPickId(defaultCampaignId)
    setNpcRememberCampaign(true)
    setNpcModalOpen(true)

    if (!shouldPrompt && defaultCampaignId) {
      void loadNpcList(defaultCampaignId, character, true)
    }
  }, [activeCampaignId, campaigns, loadNpcList])

  useEffect(()=>{
    fetchCampaigns()
    fetchCharacters()
    fetchPendingFriends()
  },[fetchCampaigns, fetchCharacters, fetchPendingFriends, profile])

  // Single source of truth: whenever activeCampaignId or the campaigns list changes,
  // align activeSession to a session that actually belongs to the active campaign.
  // If there are no sessions yet, auto-create one then align.
  // This effect is the ONLY place that writes activeSession on a campaign change —
  // handleSetActiveCampaignId deliberately only writes activeCampaignId and lets
  // this effect handle the rest so the two paths can't race.
  useEffect(()=>{
    if(!activeCampaignId) {
      setActiveSession(null)
      return
    }
    const nextCampaign = campaigns.find(c => String(c.id) === String(activeCampaignId))
    if(!nextCampaign) return
    const sessionsList: Array<any> = nextCampaign.sessions || []

    // If activeSession already belongs to this campaign keep it — no thrash.
    if (activeSession && sessionsList.some(s => String(s.id) === activeSession)) return

    if(sessionsList.length > 0){
      setActiveSession(String(sessionsList[0].id))
    } else {
      // No sessions yet — auto-create one asynchronously.
      setActiveSession(null)
      apiFetch(`/campaigns/${activeCampaignId}/create_session`, { method: 'POST' })
        .then(async res => {
          if (!res.ok) return
          const data = await res.json().catch(() => ({} as any))
          const sid = data?.session_id ? String(data.session_id) : ''
          if (sid) {
            setActiveSession(sid)
            if (data?.meta) setSessionMetaById(prev => ({ ...prev, [sid]: data.meta }))
            await fetchCampaigns()
          }
        })
        .catch(() => { /* non-fatal */ })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[activeCampaignId, campaigns])

  const handleSetActiveCampaignId = useCallback((id: string | null) => {
    // Only update the campaign ID. The useEffect above owns session alignment.
    setActiveCampaignId(id)
    // Eagerly clear the session so stale sessions from the previous campaign
    // are never briefly visible while the effect re-runs.
    setActiveSession(null)
  }, [])

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

  const quickstartPlaytest = useCallback(async (opts?: { campaignName?: string; charId?: number | null }) => {
    if (quickstartBusy) return
    setQuickstartBusy(true)
    try {
      let campaignId = activeCampaignId
      let sessionId = activeSession

      // 1) Ensure a campaign + at least one session
      if (!campaignId) {
        const label = new Date().toLocaleDateString()
        const campaignNameToUse = opts?.campaignName?.trim() || `Quickstart Campaign (${label})`
        const create = await apiFetch('/campaigns', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: campaignNameToUse,
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
        let myCharId: number | null = opts?.charId !== undefined ? opts.charId : activeCharacterId
        const hasAny = characters.length > 0
        if (myCharId === null && !hasAny) {
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
          await assignCharacterToSession(myCharId)
        }

        if (playerRunMode) {
          alert('Player-run mode is enabled for this campaign. AI scene generation was skipped.')
          return
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
    playerRunMode,
    quickstartBusy,
    assignCharacterToSession,
  ])

  const startPlaying = useCallback(async (targetCampaignId?: string) => {
    if (startPlayBusy) return
    setStartPlayBusy(true)
    const cid = targetCampaignId ?? activeCampaignId
    const isSwitching = Boolean(targetCampaignId && targetCampaignId !== activeCampaignId)
    if (isSwitching) {
      setActiveCampaignId(targetCampaignId as string)
      setActiveSession(null)
    }
    try {
      if (!cid) {
        setView('gameplay')
        alert('Select or create a campaign first.')
        return
      }

      let sessionId = isSwitching ? null : activeSession
      if (!sessionId) {
        const res = await apiFetch(`/campaigns/${cid}/create_session`, { method: 'POST' })
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
          const charId = data?.character?.id
          if (typeof charId === 'number') {
            selectedId = charId
            setActiveCharacterId(charId)
          }
          await fetchCharacters()
        }
      }

      if (selectedId !== null) {
        await assignCharacterToSession(selectedId)
      }

      if (playerRunMode) {
        alert('Player-run mode is enabled for this campaign. AI scene generation was skipped.')
        setView('gameplay')
        return
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
    assignCharacterToSession,
    playerRunMode,
    startPlayBusy,
  ])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (activeCampaignId) {
      window.localStorage.setItem('tt:lastCampaignId', String(activeCampaignId))
    }
    if (activeSession) {
      window.localStorage.setItem('tt:lastSessionId', String(activeSession))
    }
  }, [activeCampaignId, activeSession])

  const lastSessionLabel = useMemo(() => {
    if (!activeSession) return null
    return sessionMetaById[activeSession]?.name || activeSession
  }, [activeSession, sessionMetaById])

  const navigate = useCallback((v: string) => {
    setView(v)
    setDrawerOpen(false)
  }, [])

  const performModerationSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) return
    setModerationSearchBusy(true)
    try {
      const res = await apiFetch('/users/search?q=' + encodeURIComponent(q.trim()) + '&limit=5')
      if (res.ok) {
        const data = await res.json()
        setModerationSearchResults(data.results || [])
      }
    } catch { /* ignore */ }
    setModerationSearchBusy(false)
  }, [])

  return (
    <div className="dashboard-root">
      {/* Global top bar */}
      <header className="dashboard-topbar">
        <button
          className="drawer-toggle"
          type="button"
          aria-label="Open navigation menu"
          onClick={() => setDrawerOpen(true)}
        >
          <span className="drawer-toggle-icon" />
          <span className="drawer-toggle-icon" />
          <span className="drawer-toggle-icon" />
        </button>
        <span className="topbar-brand">TavernTails</span>
        <div className="topbar-right">
          <button
            className="topbar-icon-btn topbar-notif-btn"
            type="button"
            aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
            onClick={() => setNotificationsOpen(true)}
          >
            🔔
            {unreadCount > 0 && (
              <span className="notif-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
            )}
          </button>
          <button
            className="topbar-icon-btn"
            type="button"
            aria-label="Account"
            onClick={() => navigate('account')}
            title="Account"
          >
            👤
          </button>
        </div>
      </header>

      {/* Drawer overlay */}
      {drawerOpen && (
        <div className="drawer-overlay" onClick={() => setDrawerOpen(false)} />
      )}

      {/* Slide-out drawer */}
      <aside className={`dashboard-drawer ${drawerOpen ? 'drawer-open' : ''}`}>
        <div className="drawer-header">
          <div className="dashboard-brand">TavernTails</div>
          <button className="drawer-close" type="button" aria-label="Close menu" onClick={() => setDrawerOpen(false)}>✕</button>
        </div>
        <div className="dashboard-user">{profile?.name}</div>
        <nav className="dashboard-nav">
          <button className={`nav-btn ${view==='home'?'active':''}`} onClick={() => navigate('home')}>Home</button>
          <button className={`nav-btn ${view==='campaign-setup'?'active':''}`} onClick={() => navigate('campaign-setup')}>Manage Campaigns</button>
          <button className={`nav-btn ${view==='view-characters'?'active':''}`} onClick={() => navigate('view-characters')}>Manage Characters</button>
          <button className={`nav-btn ${view==='documents'?'active':''}`} onClick={() => navigate('documents')}>Documents</button>
          <button className={`nav-btn ${view==='explore'?'active':''}`} onClick={() => navigate('explore')}>Explore</button>
          <button className={`nav-btn ${view==='guides'?'active':''}`} onClick={() => navigate('guides')}>Guides</button>
          {isAdmin && (
            <button className={`nav-btn ${view==='admin'?'active':''}`} onClick={() => navigate('admin')}>Admin</button>
          )}
        </nav>
        <div className="sidebar-footer">
          <button className="btn-logout" onClick={onLogout}>Sign out</button>
        </div>
      </aside>
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
                  playerRunMode={playerRunMode}
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
                    if (key === 'home') setView('home')
                    if (key === 'gameplay') setView('gameplay')
                    if (key === 'campaign-setup') setView('campaign-setup')
                    if (key === 'view-characters') setView('view-characters')
                    if (key === 'import-character') setView('import-character')
                    if (key === 'account') setView('account')
                    if (key === 'admin') setView('admin')
                    if (key === 'contact') setContactModalOpen(true)
                    if (key === 'logout') onLogout()
                  }}
                  isAdmin={isAdmin}
                  onLogout={onLogout}
                  onSelectCharId={async (idStr) => {
                    const parsed = Number(idStr)
                    if(!Number.isFinite(parsed)) return
                    setActiveCharacterId(parsed)
                    await assignCharacterToSession(parsed)
                  }}
                />
              </div>
            </div>
          </section>
        )}
        {view === 'home' && (
          <DashboardHome
            profile={profile}
            lastSessionLabel={lastSessionLabel}
            onStartNewGame={() => {
              setQuickstartCampaignName('')
              setQuickstartCampaignNameError(null)
              setQuickstartSelectedCharId(characters.length > 0 ? String(characters[0].id) : '__none__')
              setShowQuickstartSetup(true)
            }}
            onLoadGame={() => {
              if (typeof window === 'undefined') {
                setView('gameplay')
                return
              }
              const storedCampaignId = window.localStorage.getItem('tt:lastCampaignId')
              const storedSessionId = window.localStorage.getItem('tt:lastSessionId')
              const campaign = storedCampaignId
                ? campaigns.find((c) => String(c.id) === String(storedCampaignId))
                : null
              if (campaign) {
                setActiveCampaignId(String(campaign.id))
                const sessions = Array.isArray(campaign.sessions) ? campaign.sessions : []
                const storedSession = storedSessionId
                  ? sessions.find((s: any) => String(s.id) === String(storedSessionId))
                  : null
                if (storedSession) {
                  setActiveSession(String(storedSession.id))
                } else if (sessions.length > 0) {
                  setActiveSession(String(sessions[0].id))
                }
              }
              setView('campaign-setup')
            }}
            onGoToCampaigns={() => setView('campaign-setup')}
            onGoToCharacters={() => setView('view-characters')}
            onGoToExplore={() => setView('explore')}
            onGoToGuides={() => setView('guides')}
          />
        )}
        {view === 'campaign-setup' && (
          <CampaignSetupView
            activeCampaignId={activeCampaignId}
            activeCampaign={activeCampaign}
            campaigns={campaigns}
            characters={characters}
            onSelectCampaign={handleSetActiveCampaignId}
            onCampaignUpdated={fetchCampaigns}
            onCreateCampaign={() => setShowCreateModal(true)}
            onPlay={startPlaying}
            playBusy={startPlayBusy}
            showAdminControls={isAdmin && adminMode}
            onDeleteTestCampaigns={handleDeleteTestCampaigns}
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
                    Create Character
                  </button>
                </>
              }
            />

            {characters.length === 0 ? (
              <EmptyState
                title="No characters yet"
                description="Create a character from scratch or import from a D&D Beyond PDF export."
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
              <div className="row-wrap characters-shell">
                <div className="characters-column">
                  <div className="card card-pad stack characters-list-card" style={{ gap: 10 }}>
                    <div className="muted">Characters</div>
                    <div className="stack" style={{ gap: 6 }}>
                      {characters.map((c) => {
                        const sheet = (c?.sheet && typeof c.sheet === 'object') ? c.sheet : {}
                        const importMeta = (sheet?.import && typeof sheet.import === 'object') ? sheet.import : null
                        const source = importMeta?.source ? String(importMeta.source) : ''
                        const isPicked = selectedCharacterId !== null && Number(c.id) === Number(selectedCharacterId)
                        return (
                          <button
                            key={c.id}
                            type="button"
                            className={`btn btn-quiet character-list-item ${isPicked ? 'is-active' : ''}`}
                            onClick={() => setSelectedCharacterId(Number(c.id))}
                          >
                            <div style={{ minWidth: 0 }}>
                              <div style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {c.name}{c.class_name ? ` (${c.class_name})` : ''} — L{c.level}
                              </div>
                              <div className="muted" style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {source ? `Source: ${source}` : 'Source: manual'}
                              </div>
                            </div>
                            {isPicked ? <span className="muted" style={{ fontSize: 12 }}>Selected</span> : null}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                </div>

                <div className="characters-column characters-detail">
                  {!selectedCharacter ? (
                    <div className="inline-alert" style={{ marginTop: 12 }}>
                      Select a character to view details and actions.
                    </div>
                  ) : (
                    <div className="card card-pad characters-detail-card">
                      <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                        <div style={{ fontWeight: 700 }}>
                          {selectedCharacter.name}{selectedCharacter.class_name ? ` (${selectedCharacter.class_name})` : ''} — L{selectedCharacter.level}
                        </div>
                        <div className="row-wrap" style={{ gap: 8 }}>
                          <button
                            className={`btn btn-quiet character-tab ${characterPanelMode === 'summary' ? 'active' : ''}`}
                            type="button"
                            onClick={() => setCharacterPanelMode('summary')}
                          >
                            Summary
                          </button>
                          <button
                            className={`btn btn-quiet character-tab ${characterPanelMode === 'journal' ? 'active' : ''}`}
                            type="button"
                            onClick={() => setCharacterPanelMode('journal')}
                          >
                            Journal
                          </button>
                          <button
                            className={`btn btn-quiet character-tab ${characterPanelMode === 'spells' ? 'active' : ''}`}
                            type="button"
                            onClick={() => setCharacterPanelMode('spells')}
                          >
                            Spells
                          </button>
                          <button
                            className={`btn btn-quiet character-tab ${characterPanelMode === 'features' ? 'active' : ''}`}
                            type="button"
                            onClick={() => setCharacterPanelMode('features')}
                          >
                            Features
                          </button>
                          <button
                            className={`btn btn-quiet character-tab ${characterPanelMode === 'inventory' ? 'active' : ''}`}
                            type="button"
                            onClick={() => setCharacterPanelMode('inventory')}
                          >
                            Inventory
                          </button>
                          <button
                            className="btn btn-secondary btn-icon-only"
                            type="button"
                            onClick={async () => {
                              if (!selectedCharacter) return
                              setSheetModalLoading(true)
                              setSheetModalOpen(true)
                              try {
                                const res = await apiFetch(`/characters/${selectedCharacter.id}`)
                                if (res.ok) {
                                  const data = await res.json().catch(() => ({}))
                                  setSheetModalCharacter(data?.character ?? selectedCharacter)
                                } else {
                                  setSheetModalCharacter(selectedCharacter)
                                }
                              } catch {
                                setSheetModalCharacter(selectedCharacter)
                              } finally {
                                setSheetModalLoading(false)
                              }
                            }}
                            title="Settings"
                            aria-label="Settings"
                          >
                            <SettingsIcon />
                          </button>
                        </div>
                      </div>
                      {selectedSheetSummary && characterPanelMode === 'summary' ? (
                        <div className="stack" style={{ gap: 12, marginTop: 12 }}>
                          <div className="row-wrap" style={{ gap: 16 }}>
                            <div className="card card-pad characters-subcard" style={{ flex: '1 1 220px' }}>
                              <div className="muted" style={{ marginBottom: 6 }}>Vitals</div>
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
                                <div>
                                  <div className="muted">AC</div>
                                  <div style={{ fontWeight: 700 }}>{selectedSheetSummary.ac ?? '—'}</div>
                                </div>
                                <div>
                                  <div className="muted">HP</div>
                                  <div style={{ fontWeight: 700 }}>{selectedSheetSummary.hpCurrent ?? '—'} / {selectedSheetSummary.hpMax ?? '—'}</div>
                                </div>
                                <div>
                                  <div className="muted">Speed</div>
                                  <div style={{ fontWeight: 700 }}>
                                    {typeof selectedSheetSummary.speed?.walk === 'number'
                                      ? `${selectedSheetSummary.speed.walk} ft`
                                      : '—'}
                                  </div>
                                </div>
                                <div>
                                  <div className="muted">Init</div>
                                  <div style={{ fontWeight: 700 }}>{formatModifier(selectedSheetSummary.initiative)}</div>
                                </div>
                                <div>
                                  <div className="muted">Passive</div>
                                  <div style={{ fontWeight: 700 }}>{selectedSheetSummary.passivePerception ?? '—'}</div>
                                </div>
                                <div>
                                  <div className="muted">Temp HP</div>
                                  <div style={{ fontWeight: 700 }}>{selectedSheetSummary.hpTemp ?? '—'}</div>
                                </div>
                              </div>
                            </div>

                            <div className="card card-pad characters-subcard" style={{ flex: '1 1 220px' }}>
                              <div className="muted" style={{ marginBottom: 6 }}>Abilities</div>
                              <div className="row-wrap" style={{ gap: 10 }}>
                                {(['str','dex','con','int','wis','cha'] as const).map((k) => (
                                  <div key={k} className="card" style={{ padding: '8px 10px', minWidth: 80 }}>
                                    <div className="muted" style={{ fontSize: 12 }}>{k.toUpperCase()}</div>
                                    <div style={{ fontWeight: 700 }}>{selectedSheetSummary.statScores?.[k] ?? '—'}</div>
                                    <div className="muted" style={{ fontSize: 12 }}>{formatModifier(selectedSheetSummary.statMods?.[k])}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>

                          {(selectedSheetSummary.inventory.items.length || selectedSheetSummary.skills.items.length) ? (
                            <div className="row-wrap" style={{ gap: 16 }}>
                              <div className="card card-pad characters-subcard" style={{ flex: '1 1 220px' }}>
                                <div className="muted" style={{ marginBottom: 6 }}>Inventory</div>
                                {selectedSheetSummary.inventory.items.length ? (
                                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                                    {(showAllSummaryInventory ? selectedSheetSummary.inventory.all : selectedSheetSummary.inventory.items).map((i) => <li key={i}>{i}</li>)}
                                  </ul>
                                ) : (
                                  <div className="muted">No inventory listed.</div>
                                )}
                                {!showAllSummaryInventory && selectedSheetSummary.inventory.more > 0 ? (
                                  <button className="btn btn-quiet" style={{ fontSize: 12, marginTop: 6, padding: '2px 0', color: 'var(--tt-accent, #c084fc)' }} onClick={() => setShowAllSummaryInventory(true)}>
                                    + {selectedSheetSummary.inventory.more} more — Show all
                                  </button>
                                ) : showAllSummaryInventory && selectedSheetSummary.inventory.more > 0 ? (
                                  <button className="btn btn-quiet" style={{ fontSize: 12, marginTop: 6, padding: '2px 0', color: 'var(--tt-accent, #c084fc)' }} onClick={() => setShowAllSummaryInventory(false)}>
                                    ▲ Show less
                                  </button>
                                ) : null}
                              </div>
                              <div className="card card-pad characters-subcard" style={{ flex: '1 1 220px' }}>
                                <div className="muted" style={{ marginBottom: 6 }}>Skills</div>
                                {selectedSheetSummary.skills.items.length ? (
                                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                                    {(showAllSummarySkills ? selectedSheetSummary.skills.all : selectedSheetSummary.skills.items).map((s) => <li key={s}>{s}</li>)}
                                  </ul>
                                ) : (
                                  <div className="muted">No skills listed.</div>
                                )}
                                {!showAllSummarySkills && selectedSheetSummary.skills.more > 0 ? (
                                  <button className="btn btn-quiet" style={{ fontSize: 12, marginTop: 6, padding: '2px 0', color: 'var(--tt-accent, #c084fc)' }} onClick={() => setShowAllSummarySkills(true)}>
                                    + {selectedSheetSummary.skills.more} more — Show all
                                  </button>
                                ) : showAllSummarySkills && selectedSheetSummary.skills.more > 0 ? (
                                  <button className="btn btn-quiet" style={{ fontSize: 12, marginTop: 6, padding: '2px 0', color: 'var(--tt-accent, #c084fc)' }} onClick={() => setShowAllSummarySkills(false)}>
                                    ▲ Show less
                                  </button>
                                ) : null}
                              </div>
                            </div>
                          ) : null}
                          {(() => {
                            const prof = selectedSheetSummary.proficiencies
                            const profRows: Array<{ label: string; items: string[] }> = [
                              { label: 'Languages', items: prof.languages },
                              { label: 'Armor', items: prof.armor },
                              { label: 'Weapons', items: prof.weapons },
                              { label: 'Tools', items: prof.tools },
                              { label: 'Other', items: prof.other },
                            ].filter(r => r.items.length > 0)
                            if (!profRows.length) return null
                            return (
                              <div className="card card-pad characters-subcard" style={{ marginTop: 8 }}>
                                <div className="muted" style={{ marginBottom: 6 }}>Proficiencies</div>
                                <div className="stack" style={{ gap: 4 }}>
                                  {profRows.map(row => (
                                    <div key={row.label}>
                                      <span className="muted" style={{ fontSize: 12 }}>{row.label}: </span>
                                      <span style={{ fontSize: 12 }}>{row.items.join(', ')}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )
                          })()}
                        </div>
                      ) : null}
                      {characterPanelMode === 'journal' ? (
                        <div className="card card-pad characters-subcard" style={{ marginTop: 12 }}>
                          <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                            <div className="muted">Journal</div>
                            <button className="btn btn-quiet" type="button" onClick={() => openNpcModalForCharacter(selectedCharacter)}>
                              Open Journal
                            </button>
                          </div>
                          <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
                            Review associated NPCs and campaign notes.
                          </div>
                        </div>
                      ) : null}
                      {characterPanelMode === 'spells' ? (
                        <div className="card card-pad characters-subcard" style={{ marginTop: 12 }}>
                          <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                            <div className="muted">Spells</div>
                            <button className="btn btn-secondary btn-sm" type="button" disabled>+ Add Spell</button>
                          </div>
                          {selectedCharacter ? (
                            (() => {
                              const sheet = (selectedCharacter?.sheet && typeof selectedCharacter.sheet === 'object') ? selectedCharacter.sheet : {}
                              const rawSlots: Array<{ level: number; used?: number | null; max?: number | null }> = Array.isArray((sheet as any)?.spellSlots) ? (sheet as any).spellSlots : []
                              const spellbook = Array.isArray((sheet as any)?.spellbook) ? (sheet as any).spellbook : []
                              const spellNames = Array.isArray((sheet as any)?.spells) ? (sheet as any).spells : []
                              const rows = spellbook.length
                                ? spellbook
                                : spellNames.map((name: any) => ({ name: String(name) }))

                              // Build slot map: level -> {max, used}
                              const slotMap = new Map<number, { max: number; used: number }>(
                                rawSlots.map(s => [s.level, { max: s.max ?? 0, used: s.used ?? 0 }])
                              )

                              // Helper to parse level number from header string
                              const headerToLevel = (header: string | null): number | null => {
                                if (!header) return null
                                if (/cantrip/i.test(header)) return 0
                                const m = header.match(/^(\d+)/)
                                return m ? parseInt(m[1], 10) : null
                              }

                              const toggleSpellSlot = async (level: number, slotIndex: number) => {
                                if (!selectedCharacter) return
                                const current = slotMap.get(level)
                                if (!current) return
                                // Clicking a used slot (index < used) restores slots from that point.
                                // Clicking an available slot (index >= used) uses slots up to and including it.
                                const newUsed = slotIndex < current.used ? slotIndex : slotIndex + 1
                                // Optimistically update local state
                                const updatedSlots = rawSlots.map(s =>
                                  s.level === level ? { ...s, used: newUsed } : s
                                )
                                // Persist to server
                                try {
                                  const existingSheet = (selectedCharacter?.sheet && typeof selectedCharacter.sheet === 'object') ? { ...selectedCharacter.sheet } : {}
                                  await apiFetch(`/characters/${selectedCharacter.id}`, {
                                    method: 'PUT',
                                    body: JSON.stringify({ sheet: { ...existingSheet, spellSlots: updatedSlots } }),
                                  })
                                  await fetchCharacters()
                                } catch {
                                  // silent
                                }
                              }

                              return (
                                <>
                                  {rows.length === 0 ? (
                                    <div className="muted">No spells parsed.</div>
                                  ) : (
                                    (() => {
                                      let lastHeader: string | null = null
                                      const groups: Array<{ header: string | null; rows: typeof rows }> = []
                                      for (const row of rows) {
                                        const header = typeof row?.header === 'string' ? row.header.trim() : ''
                                        if (header && header !== lastHeader) {
                                          groups.push({ header, rows: [row] })
                                          lastHeader = header
                                        } else if (groups.length === 0) {
                                          groups.push({ header: null, rows: [row] })
                                        } else {
                                          groups[groups.length - 1].rows.push(row)
                                        }
                                      }
                                      return (
                                        <div className="stack" style={{ gap: 6 }}>
                                          {groups.map((group, gi) => {
                                            const lvl = headerToLevel(group.header)
                                            const slotInfo = (lvl !== null && lvl > 0) ? slotMap.get(lvl) : undefined
                                            return (
                                              <div key={gi}>
                                                {group.header ? (
                                                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 11, padding: '4px 0 4px', opacity: 0.85, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                                                    <span>{group.header}</span>
                                                    {slotInfo && slotInfo.max > 0 ? (
                                                      <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                                                        {Array.from({ length: slotInfo.max }).map((_, i) => (
                                                          <button
                                                            key={i}
                                                            type="button"
                                                            title={`Slot ${i + 1}: ${i < slotInfo.used ? 'used (click to restore)' : 'available (click to use)'}`}
                                                            onClick={() => lvl !== null && toggleSpellSlot(lvl, i)}
                                                            style={{
                                                              display: 'inline-block',
                                                              width: 12,
                                                              height: 12,
                                                              borderRadius: '50%',
                                                              border: '1px solid rgba(255,255,255,0.5)',
                                                              background: i < slotInfo.used ? 'rgba(255,255,255,0.15)' : 'rgba(173,136,95,0.7)',
                                                              cursor: 'pointer',
                                                              padding: 0,
                                                            }}
                                                          />
                                                        ))}
                                                        <span className="muted" style={{ fontSize: 10, marginLeft: 2 }}>{slotInfo.used}/{slotInfo.max}</span>
                                                      </div>
                                                    ) : null}
                                                  </div>
                                                ) : null}
                                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                                                  {group.rows.map((row: any, idx: number) => {
                                                    const isExpanded = selectedSpellRow?.name === row?.name
                                                    const hasDetails = row?.source || row?.time || row?.range || row?.components || row?.duration || row?.save_hit || row?.notes || row?.page
                                                    return (
                                                      <React.Fragment key={`${row?.name || 'spell'}-${idx}`}>
                                                        <button
                                                          type="button"
                                                          className="btn btn-quiet"
                                                          style={{
                                                            textAlign: 'left',
                                                            background: isExpanded ? 'rgba(173,136,95,0.20)' : 'rgba(0,0,0,0.10)',
                                                            borderRadius: 6,
                                                            padding: '5px 8px',
                                                            fontSize: 12,
                                                            gridColumn: isExpanded ? 'span 2' : undefined,
                                                          }}
                                                          onClick={() => setSelectedSpellRow(isExpanded ? null : row)}
                                                        >
                                                          <span style={{ fontWeight: 600, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row?.name || '—'}</span>
                                                          {row?.slot_header ? <span className="muted" style={{ fontSize: 10 }}>{row.slot_header}</span> : null}
                                                        </button>
                                                        {isExpanded && hasDetails ? (
                                                          <div className="card card-pad" style={{ fontSize: 12, background: 'rgba(0,0,0,0.15)', gridColumn: 'span 2', marginLeft: 0 }}>
                                                            <div className="row-wrap" style={{ gap: 10, flexWrap: 'wrap' }}>
                                                              {row?.source ? <div><span className="muted">Source:</span> {row.source}</div> : null}
                                                              {row?.save_hit ? <div><span className="muted">Save/Atk:</span> {row.save_hit}</div> : null}
                                                              {row?.time ? <div><span className="muted">Cast Time:</span> {row.time}</div> : null}
                                                              {row?.range ? <div><span className="muted">Range:</span> {row.range}</div> : null}
                                                              {row?.components ? <div><span className="muted">Components:</span> {row.components}</div> : null}
                                                              {row?.duration ? <div><span className="muted">Duration:</span> {row.duration}</div> : null}
                                                              {row?.page ? <div><span className="muted">Page:</span> {row.page}</div> : null}
                                                              {row?.notes ? <div style={{ width: '100%' }}><span className="muted">Notes:</span> {row.notes}</div> : null}
                                                            </div>
                                                          </div>
                                                        ) : null}
                                                      </React.Fragment>
                                                    )
                                                  })}
                                                </div>
                                              </div>
                                            )
                                          })}
                                        </div>
                                      )
                                    })()
                                  )}
                                </>
                              )
                            })()
                          ) : (
                            <div className="muted">No spells parsed.</div>
                          )}
                        </div>
                      ) : null}
                      {characterPanelMode === 'features' ? (
                        <div className="card card-pad characters-subcard" style={{ marginTop: 12 }}>
                          <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                            <div className="muted">Features</div>
                            <button className="btn btn-secondary btn-sm" type="button" disabled>+ Add Feature</button>
                          </div>
                          {selectedSheetSummary ? (
                            <>
                              {selectedSheetSummary.featureGroups.length > 0 ? (
                                (() => {
                                  const FEATURE_LIMIT = 15
                                  const allItems = selectedSheetSummary.features.items
                                  const visibleItems = showAllFeatures ? allItems : allItems.slice(0, FEATURE_LIMIT)
                                  const hiddenCount = allItems.length - visibleItems.length
                                  const visibleNames = new Set(visibleItems.map(f => f.name))
                                  return (
                                    <div className="stack" style={{ gap: 8 }}>
                                      {selectedSheetSummary.featureGroups.map((group, gi) => {
                                        const groupItems = showAllFeatures
                                          ? group.items
                                          : group.items.filter(f => visibleNames.has(f.name))
                                        if (!groupItems.length) return null
                                        return (
                                          <div key={`group-${gi}`}>
                                            <div style={{ fontWeight: 700, fontSize: 11, padding: '4px 0 4px', opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{group.label}</div>
                                            <div className="stack" style={{ gap: 4 }}>
                                              {groupItems.map((f, idx) => {
                                                const isExpanded = selectedFeatureRow?.name === f.name
                                                const hasDetails = Boolean(f.description || f.source)
                                                return (
                                                  <React.Fragment key={`${f.name}-${idx}`}>
                                                    <button
                                                      type="button"
                                                      className="btn btn-quiet"
                                                      style={{
                                                        textAlign: 'left',
                                                        justifyContent: 'space-between',
                                                        background: isExpanded ? 'rgba(173,136,95,0.20)' : undefined,
                                                        borderRadius: 6,
                                                        padding: '6px 10px',
                                                        fontSize: 13,
                                                      }}
                                                      onClick={() => setSelectedFeatureRow(isExpanded ? null : f)}
                                                    >
                                                      <span style={{ fontWeight: 600 }}>{f.name}</span>
                                                      {hasDetails ? <span className="muted" style={{ fontSize: 11 }}>{isExpanded ? '▲' : '▼'}</span> : null}
                                                    </button>
                                                    {isExpanded && hasDetails ? (
                                                      <div className="card card-pad" style={{ fontSize: 12, background: 'rgba(0,0,0,0.15)', marginLeft: 8 }}>
                                                        {f.description ? <div style={{ lineHeight: 1.5 }}>{f.description}</div> : null}
                                                      </div>
                                                    ) : null}
                                                  </React.Fragment>
                                                )
                                              })}
                                            </div>
                                          </div>
                                        )
                                      })}
                                      {hiddenCount > 0 ? (
                                        <button
                                          type="button"
                                          className="btn btn-quiet"
                                          style={{ fontSize: 12, padding: '4px 10px', color: 'var(--tt-accent, #c084fc)' }}
                                          onClick={() => setShowAllFeatures(true)}
                                        >
                                          + {hiddenCount} more — Show all
                                        </button>
                                      ) : allItems.length > FEATURE_LIMIT ? (
                                        <button
                                          type="button"
                                          className="btn btn-quiet"
                                          style={{ fontSize: 12, padding: '4px 10px', color: 'var(--tt-accent, #c084fc)' }}
                                          onClick={() => setShowAllFeatures(false)}
                                        >
                                          ▲ Show less
                                        </button>
                                      ) : null}
                                    </div>
                                  )
                                })()
                              ) : (
                                <div className="muted">No features parsed.</div>
                              )}
                            </>
                          ) : (
                            <div className="muted">No features parsed.</div>
                          )}
                        </div>
                      ) : null}
                      {characterPanelMode === 'inventory' ? (
                        <div className="card card-pad characters-subcard" style={{ marginTop: 12 }}>
                          <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                            <div className="muted">Inventory</div>
                            <button className="btn btn-secondary btn-sm" type="button" disabled>+ Add Item</button>
                          </div>
                          {selectedSheetSummary ? (
                            selectedSheetSummary.inventory.all.length ? (
                              <div className="stack" style={{ gap: 4 }}>
                                {(showAllInventoryPanel ? selectedSheetSummary.inventory.all : selectedSheetSummary.inventory.items).map((item) => (
                                  <div key={item} className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', padding: '5px 8px', background: 'rgba(0,0,0,0.12)', borderRadius: 6, fontSize: 13 }}>
                                    <span>{item}</span>
                                    <button className="btn btn-quiet btn-sm" type="button" disabled style={{ opacity: 0.5, fontSize: 11 }}>✕</button>
                                  </div>
                                ))}
                                {!showAllInventoryPanel && selectedSheetSummary.inventory.more > 0 ? (
                                  <button className="btn btn-quiet" style={{ fontSize: 12, padding: '4px 10px', color: 'var(--tt-accent, #c084fc)' }} onClick={() => setShowAllInventoryPanel(true)}>
                                    + {selectedSheetSummary.inventory.more} more items — Show all
                                  </button>
                                ) : showAllInventoryPanel && selectedSheetSummary.inventory.more > 0 ? (
                                  <button className="btn btn-quiet" style={{ fontSize: 12, padding: '4px 10px', color: 'var(--tt-accent, #c084fc)' }} onClick={() => setShowAllInventoryPanel(false)}>
                                    ▲ Show less
                                  </button>
                                ) : null}
                              </div>
                            ) : (
                              <div className="muted">No inventory items.</div>
                            )
                          ) : (
                            <div className="muted">No inventory data.</div>
                          )}
                        </div>
                      ) : null}
                    </div>
                  )}
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
          onSaved={async () => {
            await fetchCharacters()
          }}
        />

        <ContactModal open={contactModalOpen} onClose={() => setContactModalOpen(false)} />

        <BlockReportModal
          open={blockReportModalOpen}
          targetUser={blockReportTarget}
          initialMode={blockReportMode}
          onClose={() => setBlockReportModalOpen(false)}
          onBlocked={() => setModerationSearchResults([])}
        />

        <Modal
          open={npcModalOpen}
          title={npcModalCharacter?.name ? `Journal — ${npcModalCharacter.name}` : 'Journal'}
          onClose={() => {
            setNpcModalOpen(false)
            setNpcModalItems([])
            setNpcModalError(null)
            setNpcModalCampaignId(null)
            setNpcCampaignPickId(null)
          }}
        >
          <div className="stack" style={{ gap: 12 }}>
            {npcModalError ? (
              <div className="inline-alert inline-alert-error">{npcModalError}</div>
            ) : null}

            <div className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="stack" style={{ gap: 6 }}>
                <label className="muted">Campaign</label>
                <select
                  className="input"
                  value={npcCampaignPickId || ''}
                  onChange={(e) => setNpcCampaignPickId(e.target.value || null)}
                  disabled={npcModalBusy}
                >
                  <option value="">Select a campaign</option>
                  {campaigns.map((c) => (
                    <option key={String(c.id)} value={String(c.id)}>{c.name}</option>
                  ))}
                </select>
              </div>

              <label className="row" style={{ gap: 8, userSelect: 'none' }}>
                <input
                  type="checkbox"
                  checked={npcRememberCampaign}
                  onChange={(e) => setNpcRememberCampaign(e.target.checked)}
                  disabled={npcModalBusy}
                />
                <span className="muted">Remember this campaign for this character</span>
              </label>
            </div>

            <div className="row-wrap" style={{ justifyContent: 'flex-end', gap: 8 }}>
              <button
                className="btn btn-secondary"
                type="button"
                disabled={!npcCampaignPickId || npcModalBusy}
                onClick={async () => {
                  if (!npcCampaignPickId || !npcModalCharacter) return
                  await loadNpcList(npcCampaignPickId, npcModalCharacter, npcRememberCampaign)
                }}
              >
                {npcModalBusy ? 'Loading…' : 'Load NPCs'}
              </button>
            </div>

            {npcModalCampaignId && npcModalItems.length === 0 && !npcModalBusy ? (
              <div className="inline-alert">No associated NPCs found for this campaign yet.</div>
            ) : null}

            {npcModalItems.length > 0 ? (
              <div className="stack" style={{ gap: 10 }}>
                {npcModalItems.map((npc, idx) => (
                  <div key={`${npc.name}-${idx}`} className="card card-pad">
                    <div style={{ fontWeight: 700 }}>{npc.name}</div>
                    {npc.motivations?.length ? (
                      <div className="muted" style={{ marginTop: 6 }}>
                        Motivations: {npc.motivations.join(', ')}
                      </div>
                    ) : null}
                    {npc.quirks?.length ? (
                      <div className="muted" style={{ marginTop: 6 }}>
                        Quirks: {npc.quirks.join(', ')}
                      </div>
                    ) : null}
                    {npc.traits && Object.keys(npc.traits).length ? (
                      <div style={{ marginTop: 8 }}>
                        <div className="muted" style={{ marginBottom: 4 }}>Traits</div>
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                          {Object.entries(npc.traits).map(([key, value]) => (
                            <li key={key} className="muted">{key}: {String(value)}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </Modal>

        <Modal
          open={characterSettingsOpen}
          title="Character settings"
          onClose={() => setCharacterSettingsOpen(false)}
        >
          <div className="stack" style={{ gap: 12 }}>
            {!selectedCharacter ? (
              <div className="muted">Select a character first.</div>
            ) : (
              <>
                <div className="muted">
                  {selectedCharacter.name}{selectedCharacter.class_name ? ` (${selectedCharacter.class_name})` : ''} — L{selectedCharacter.level}
                </div>
                <div className="row-wrap" style={{ gap: 8 }}>
                  {(() => {
                    const isSelected = activeCharacterId !== null && Number(selectedCharacter.id) === Number(activeCharacterId)
                    return (
                      <button
                        className="btn"
                        type="button"
                        disabled={!activeSession || isSelected}
                        onClick={async () => {
                          setActiveCharacterId(selectedCharacter.id)
                          await assignCharacterToSession(selectedCharacter.id)
                          setCharacterSettingsOpen(false)
                        }}
                      >
                        {isSelected ? 'Assigned to session' : 'Assign to session'}
                      </button>
                    )
                  })()}
                  <button
                    className="btn btn-quiet"
                    type="button"
                    disabled={!activeSession || activeCharacterId === null}
                    onClick={async () => {
                      setActiveCharacterId(null)
                      await assignCharacterToSession(null)
                      setCharacterSettingsOpen(false)
                    }}
                  >
                    Clear session character
                  </button>
                  <button
                    className="btn btn-quiet"
                    type="button"
                    onClick={async () => {
                      if (!selectedCharacter) return
                      if (!window.confirm('Re-parse spell data from PDF? This will attempt to fix any spell import issues.')) return
                      const characterId = Number(selectedCharacter.id)
                      if (!Number.isFinite(characterId)) {
                        alert('Invalid character ID')
                        return
                      }
                      try {
                        await fetch(`/api/characters/${characterId}/reparse-spells`, {
                          method: 'POST',
                          credentials: 'include'
                        })
                        alert('Spells re-parsed successfully')
                        fetchCharacters()
                      } catch (err) {
                        console.error('Failed to reparse spells:', err)
                        alert('Failed to reparse spells')
                      }
                    }}
                  >
                    Re-parse Spells
                  </button>
                  <button
                    className="btn"
                    type="button"
                    onClick={async () => {
                      if (!selectedCharacter) return
                      if (!window.confirm('Delete this character?')) return
                      const characterId = Number(selectedCharacter.id)
                      if (!Number.isFinite(characterId)) {
                        alert('Delete failed: invalid character id.')
                        return
                      }
                      try {
                        const res = await apiFetch(`/characters/${characterId}`, { method: 'DELETE' })
                        if (!res.ok) {
                          const detail = await res.json().catch(() => null)
                          const message = detail?.detail || detail?.message || `Delete failed (${res.status}).`
                          alert(message)
                          return
                        }
                        if (activeCharacterId !== null && Number(characterId) === Number(activeCharacterId)) {
                          setActiveCharacterId(null)
                          await assignCharacterToSession(null)
                        }
                        setCharacters((prev) => prev.filter((c) => Number(c?.id) !== Number(characterId)))
                        setSelectedCharacterId(null)
                        setCharacterSettingsOpen(false)
                        await fetchCharacters()
                      } catch (err) {
                        alert('Network error. Please try again.')
                      }
                    }}
                    style={{ background: '#E09A4F', color: '#332A21' }}
                    title="Delete character"
                    aria-label="Delete character"
                  >
                    <DeleteIcon />
                    Delete
                  </button>
                </div>
              </>
            )}
          </div>
        </Modal>

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
                      await assignCharacterToSession(createdId)
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
            onAssignCharacterToSession={assignCharacterToSession}
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

        {view === 'explore' && (
          <section className="dashboard-panel stack">
            <PageHeader
              title="Explore"
              subtitle="Browse lore and world details revealed through your adventures."
            />
            <div className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
              <div className="muted" style={{ marginBottom: 8 }}>Campaign Lore</div>
              <div className="muted" style={{ fontSize: 13 }}>
                As you play through campaigns, lore and world details discovered by your characters will appear here.
                Select a campaign to browse its discovered lore.
              </div>
              {campaigns.length > 0 ? (
                <div className="stack" style={{ gap: 8, marginTop: 12 }}>
                  {campaigns.map((c) => (
                    <button
                      key={c.id}
                      className={`btn btn-quiet ${String(c.id) === String(activeCampaignId) ? 'active' : ''}`}
                      type="button"
                      onClick={() => handleSetActiveCampaignId(String(c.id))}
                    >
                      {c.name}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="inline-alert" style={{ marginTop: 12 }}>
                  No campaigns yet. Start a campaign to begin discovering lore.
                </div>
              )}
            </div>
          </section>
        )}

        {view === 'guides' && (
          <section className="dashboard-panel stack">
            <PageHeader
              title="Guides"
              subtitle="Best practices for using TavernTails tools and systems."
            />
            <div className="stack" style={{ gap: 12 }}>
              {[
                { title: 'Getting Started', body: 'Create a campaign, import or create your character, then start your first session.' },
                { title: 'Importing Characters', body: 'Import characters via PDF export. Use "Manage Characters → Import" to get started. The Beyond 20 browser extension can also relay your rolls directly into TavernTails.' },
                { title: 'AI Game Master', body: 'The AI GM narrates scenes, prompts dice rolls, and tracks NPCs. Use the campaign settings to assign an AI or human GM.' },
                { title: 'Managing Documents', body: 'Upload campaign PDFs, rule sets, or random tables under Documents. These inform the AI during gameplay.' },
                { title: 'Player-Run Mode', body: 'Enable player-run mode in campaign settings if a human GM is running the session. AI still handles notes and NPC tracking.' },
              ].map((guide) => (
                <div key={guide.title} className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>{guide.title}</div>
                  <div className="muted" style={{ fontSize: 13 }}>{guide.body}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {view === 'documents' && (
          <section className="dashboard-panel stack">
            <PageHeader
              title="Documents"
              subtitle="Manage documents for your campaigns and characters."
            />
            <div className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Reusable Library</div>
              <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                Upload PDFs, campaign modules, random tables, and reference documents. These can be used across campaigns.
              </div>
              <div className="row-wrap" style={{ gap: 8 }}>
                <button className="btn" type="button">Upload Document</button>
              </div>
              <div className="inline-alert" style={{ marginTop: 12 }}>
                No documents uploaded yet.
              </div>
            </div>
            {campaigns.length > 0 && (
              <div className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Campaign Documents</div>
                <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                  Documents organized by campaign.
                </div>
                <div className="stack" style={{ gap: 8 }}>
                  {campaigns.map((c) => (
                    <div key={c.id} className="card card-pad" style={{ background: 'rgba(71,66,61,0.5)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontWeight: 600 }}>{c.name}</div>
                        <button
                          className="btn btn-secondary btn-sm"
                          type="button"
                          onClick={() => {
                            setActiveCampaignId(String(c.id))
                            const sessions = Array.isArray(c.sessions) ? c.sessions : []
                            if (sessions.length > 0) setActiveSession(String(sessions[0].id))
                            setView('gameplay')
                            setTimeout(() => {
                              window.dispatchEvent(new CustomEvent('gameplay:open-documents'))
                            }, 200)
                          }}
                        >
                          View Docs
                        </button>
                      </div>
                      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                        {Array.isArray(c.sessions) ? c.sessions.length : 0} session{(Array.isArray(c.sessions) ? c.sessions.length : 0) !== 1 ? 's' : ''}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {characters.length > 0 && (
              <div className="card card-pad" style={{ background: 'var(--surface-dark)' }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Character Documents</div>
                <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
                  Documents associated with your characters.
                </div>
                <div className="stack" style={{ gap: 8 }}>
                  {characters.map((c) => (
                    <div key={c.id} className="card card-pad" style={{ background: 'rgba(71,66,61,0.5)' }}>
                      <div style={{ fontWeight: 600 }}>{c.name}</div>
                      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>No documents yet.</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}


        {view === 'beyond20' && (
          <Beyond20View
            activeSessionId={activeSession}
            identifier={profile?.email || profile?.username || null}
          />
        )}

        {view === 'account' && (
          <section className="dashboard-panel stack">
            {(() => {
              const displayName = String(profile?.name || profile?.username || 'Adventurer')
              const email = String(profile?.email || '—')
              const username = String(profile?.username || '—')
              const userId = profile?.id ?? profile?.user_id ?? '—'
              const createdAt = profile?.created_at || profile?.createdAt || null
              const preferences = (profile?.preferences && typeof profile.preferences === 'object') ? profile.preferences : {}
              const preferenceEntries = Object.entries(preferences)
              const initials = displayName
                .split(' ')
                .map((p) => p.trim()[0])
                .filter(Boolean)
                .slice(0, 2)
                .join('')
                .toUpperCase()

              const friends = Array.isArray(profile?.friends) ? profile.friends : []
              const friendCount = typeof profile?.friend_count === 'number' ? profile.friend_count : friends.length
              const providers = Array.isArray(profile?.providers) ? profile.providers : []
              const oauth = profile?.oauth && typeof profile.oauth === 'object' ? profile.oauth : {}
              const linkedProviderSet = new Set<string>([
                ...providers.map((p: any) => String(p).toLowerCase()),
                ...Object.keys(oauth).map((p) => String(p).toLowerCase()),
              ])
              const providerOptions = [
                { id: 'google', label: 'Google' },
                { id: 'discord', label: 'Discord' },
                { id: 'twitch', label: 'Twitch' },
              ]

              return (
                <>
                  <PageHeader
                    title="Account"
                    subtitle="Manage profile, emails, security, and linked accounts."
                  />

                  <div className="account-tabs" style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
                    {(['profile', 'inbox', 'tickets'] as const).map(t => (
                      <button
                        key={t}
                        type="button"
                        className={`btn btn-sm${accountTab === t ? '' : ' btn-secondary'}`}
                        onClick={() => setAccountTab(t)}
                      >
                        {t === 'profile' ? 'Profile' : t === 'inbox' ? '📨 Inbox' : '🎫 My Issues'}
                      </button>
                    ))}
                  </div>

                  {accountTab === 'inbox' ? (
                    <InboxPanel profile={profile} visible={accountTab === 'inbox'} />
                  ) : accountTab === 'tickets' ? (
                    <MyTicketsPanel visible={accountTab === 'tickets'} onContact={() => setContactModalOpen(true)} />
                  ) : (
                   <>
                   <div className="account-grid">
                    <div className="card card-pad account-card">
                      <div className="account-header">
                        <div className="account-avatar">{initials || 'TT'}</div>
                        <div>
                          <div className="account-name">{displayName}</div>
                          <div className="muted">{email}</div>
                        </div>
                      </div>
                      <div className="account-kv">
                        <div>
                          <div className="muted">Username</div>
                          <div>{username}</div>
                        </div>
                        <div>
                          <div className="muted">User ID</div>
                          <div>{String(userId)}</div>
                        </div>
                        <div>
                          <div className="muted">Email verified</div>
                          <div>{profile?.verified ? 'Yes' : 'No'}</div>
                        </div>
                        <div>
                          <div className="muted">Created</div>
                          <div>{createdAt ? new Date(createdAt).toLocaleString() : '—'}</div>
                        </div>
                      </div>
                      <div className="row-wrap" style={{ marginTop: 10 }}>
                        <button className="btn btn-secondary" type="button" onClick={() => { setAccountEditMode(true); setAccountSaveMsg(null) }}>
                          Edit Profile
                        </button>
                      </div>
                    </div>

                    {accountEditMode ? (
                    <div className="card card-pad account-card">
                      <div style={{ fontWeight: 700, marginBottom: 8 }}>Edit Profile</div>
                      {accountSaveMsg ? (
                        <div className={`inline-alert ${accountSaveMsg.kind === 'error' ? 'inline-alert-error' : ''}`} style={{ marginBottom: 10 }}>
                          {accountSaveMsg.text}
                        </div>
                      ) : null}
                      <div className="stack" style={{ gap: 10 }}>
                        <div>
                          <label className="muted" style={{ fontSize: 12 }}>Display Name</label>
                          <input
                            className="input"
                            value={accountEditName !== null ? accountEditName : displayName}
                            onChange={(e) => setAccountEditName(e.target.value)}
                            placeholder="Display name"
                            disabled={accountSaving}
                          />
                        </div>
                        <div>
                          <label className="muted" style={{ fontSize: 12 }}>Username</label>
                          <input
                            className="input"
                            value={accountEditUsername !== null ? accountEditUsername : (profile?.username || '')}
                            onChange={(e) => setAccountEditUsername(e.target.value)}
                            placeholder="Username (optional)"
                            disabled={accountSaving}
                          />
                        </div>
                        <div>
                          <label className="muted" style={{ fontSize: 12 }}>Email</label>
                          <input
                            className="input"
                            type="email"
                            value={accountEditEmail !== null ? accountEditEmail : (profile?.email || '')}
                            onChange={(e) => setAccountEditEmail(e.target.value)}
                            placeholder="Email address"
                            disabled={accountSaving}
                          />
                        </div>
                        <div className="row-wrap" style={{ gap: 8 }}>
                          <button
                            className="btn"
                            type="button"
                            disabled={accountSaving}
                            onClick={async () => {
                              setAccountSaving(true)
                              setAccountSaveMsg(null)
                              try {
                                const payload: any = {}
                                const newName = (accountEditName !== null ? accountEditName : displayName).trim()
                                const newEmail = (accountEditEmail !== null ? accountEditEmail : (profile?.email || '')).trim()
                                const newUsername = (accountEditUsername !== null ? accountEditUsername : (profile?.username || '')).trim()
                                if (!newName) {
                                  throw new Error('Display name cannot be empty.')
                                }
                                if (newEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newEmail)) {
                                  throw new Error('Please enter a valid email address.')
                                }
                                if (accountEditName !== null && newName !== displayName) {
                                  payload.name = newName
                                }
                                if (accountEditEmail !== null && newEmail !== (profile?.email || '')) {
                                  payload.email = newEmail
                                }
                                if (accountEditUsername !== null && newUsername !== (profile?.username || '') && newUsername) {
                                  payload.username = newUsername
                                }
                                if (Object.keys(payload).length === 0) {
                                  setAccountSaveMsg({ kind: 'info', text: 'No changes to save.' })
                                  return
                                }
                                const res = await apiFetch('/player/me', {
                                  method: 'PUT',
                                  headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify(payload),
                                })
                                if (!res.ok) {
                                  const err = await res.json().catch(() => null)
                                  throw new Error(err?.detail || 'Failed to update profile')
                                }
                                const data = await res.json()
                                // If the server issued a fresh token (email changed), persist it.
                                if (data.access_token) {
                                  localStorage.setItem('access_token', data.access_token)
                                }
                                setAccountSaveMsg({ kind: 'info', text: 'Profile updated.' })
                                setAccountEditName(null)
                                setAccountEditEmail(null)
                                setAccountEditUsername(null)
                                setAccountEditMode(false)
                              } catch (e: any) {
                                setAccountSaveMsg({ kind: 'error', text: e?.message || 'Failed to update profile' })
                              } finally {
                                setAccountSaving(false)
                              }
                            }}
                          >
                            {accountSaving ? 'Saving…' : 'Save Changes'}
                          </button>
                          <button
                            className="btn btn-secondary"
                            type="button"
                            disabled={accountSaving}
                            onClick={() => {
                              setAccountEditName(null)
                              setAccountEditEmail(null)
                              setAccountEditUsername(null)
                              setAccountSaveMsg(null)
                              setAccountEditMode(false)
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    </div>
                    ) : null}

                    <div className="card card-pad account-card">
                      <div style={{ fontWeight: 750, marginBottom: 8 }}>Friends</div>
                      <div className="account-kv">
                        <div>
                          <div className="muted">Total friends</div>
                          <div>{friendCount}</div>
                        </div>
                      </div>
                      {friends.length ? (
                        <div className="account-list">
                          {friends.slice(0, 3).map((friend: any, idx: number) => (
                            <div key={`${friend?.id ?? idx}`} className="account-pill">
                              {String(friend?.name ?? friend?.username ?? friend?.email ?? `Friend ${idx + 1}`)}
                            </div>
                          ))}
                          {friends.length > 3 ? (
                            <div className="account-pill">+{friends.length - 3} more</div>
                          ) : null}
                        </div>
                      ) : (
                        <div className="muted" style={{ fontSize: 13 }}>
                          Add friends to share campaigns and invite players.
                        </div>
                      )}
                    </div>

                    <div
                      id="account-invites"
                      ref={invitesCardRef}
                      className={`card card-pad account-card ${accountSection === 'invites' ? 'account-card--highlight' : ''}`}
                    >
                      <div style={{ fontWeight: 750, marginBottom: 8 }}>
                        Pending Invites
                        {pendingFriendRequests.length > 0 && (
                          <span className="notif-badge-inline">{pendingFriendRequests.length}</span>
                        )}
                      </div>
                      {pendingFriendRequests.length === 0 ? (
                        <div className="muted" style={{ fontSize: 13 }}>No pending invites.</div>
                      ) : (
                        <div className="stack" style={{ gap: 8 }}>
                          {pendingFriendRequests.map((req: any) => {
                            const fromProfile = req?.from_profile || {}
                            const fromName = fromProfile?.name || fromProfile?.username || fromProfile?.email || `User ${req?.from_id}`
                            return (
                              <div key={req?.from_id} className="row-wrap" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8, padding: '8px 0', borderBottom: '1px solid var(--tt-border)' }}>
                                <div>
                                  <div style={{ fontWeight: 600 }}>{fromName}</div>
                                  <div className="muted" style={{ fontSize: 12 }}>Friend request</div>
                                </div>
                                <div className="row-wrap" style={{ gap: 6 }}>
                                  <button
                                    className="btn btn-sm"
                                    type="button"
                                    onClick={async () => {
                                      try {
                                        const res = await apiFetch('/player/friends/accept', {
                                          method: 'POST',
                                          body: JSON.stringify({ from_identifier: fromProfile?.email || fromProfile?.username || String(req?.from_id) }),
                                        })
                                        if (res.ok) {
                                          setPendingFriendRequests((prev) => prev.filter((r: any) => r?.from_id !== req?.from_id))
                                          setReadNotificationIds((prev) => [...prev, `friend-invite-${req?.from_id}`])
                                        }
                                      } catch (e) { /* ignore */ }
                                    }}
                                  >
                                    Accept
                                  </button>
                                  <button
                                    className="btn btn-secondary btn-sm"
                                    type="button"
                                    onClick={() => {
                                      setPendingFriendRequests((prev) => prev.filter((r: any) => r?.from_id !== req?.from_id))
                                      setReadNotificationIds((prev) => [...prev, `friend-invite-${req?.from_id}`])
                                    }}
                                  >
                                    Dismiss
                                  </button>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>

                    <div className="card card-pad account-card">
                      <div style={{ fontWeight: 750, marginBottom: 8 }}>Security</div>
                      <div className="muted" style={{ fontSize: 13 }}>
                        Keep your account secure with verified email, strong passwords, and linked providers.
                      </div>
                      {!changePwOpen ? (
                        <div className="row-wrap" style={{ marginTop: 10 }}>
                          <button className="btn btn-secondary" type="button" onClick={() => { setChangePwOpen(true); setChangePwMsg(null) }}>
                            Change password
                          </button>
                        </div>
                      ) : (
                        <div className="stack" style={{ gap: 10, marginTop: 10 }}>
                          {changePwMsg && (
                            <div className={`inline-alert ${changePwMsg.kind === 'error' ? 'inline-alert-error' : ''}`}>
                              {changePwMsg.text}
                            </div>
                          )}
                          <div>
                            <label className="muted" style={{ fontSize: 12 }}>Current password</label>
                            <input
                              className="input"
                              type="password"
                              value={changePwCurrent}
                              onChange={(e) => setChangePwCurrent(e.target.value)}
                              placeholder="Current password"
                              disabled={changePwBusy}
                            />
                          </div>
                          <div>
                            <label className="muted" style={{ fontSize: 12 }}>New password (min 8 characters)</label>
                            <input
                              className="input"
                              type="password"
                              value={changePwNew}
                              onChange={(e) => setChangePwNew(e.target.value)}
                              placeholder="New password"
                              disabled={changePwBusy}
                            />
                          </div>
                          <div>
                            <label className="muted" style={{ fontSize: 12 }}>Confirm new password</label>
                            <input
                              className="input"
                              type="password"
                              value={changePwConfirm}
                              onChange={(e) => setChangePwConfirm(e.target.value)}
                              placeholder="Confirm new password"
                              disabled={changePwBusy}
                            />
                          </div>
                          <div className="row-wrap" style={{ gap: 8 }}>
                            <button
                              className="btn"
                              type="button"
                              disabled={changePwBusy}
                              onClick={async () => {
                                setChangePwMsg(null)
                                if (!changePwCurrent) {
                                  setChangePwMsg({ kind: 'error', text: 'Current password is required.' })
                                  return
                                }
                                if (changePwNew.length < 8) {
                                  setChangePwMsg({ kind: 'error', text: 'New password must be at least 8 characters.' })
                                  return
                                }
                                if (changePwNew !== changePwConfirm) {
                                  setChangePwMsg({ kind: 'error', text: 'Passwords do not match.' })
                                  return
                                }
                                setChangePwBusy(true)
                                try {
                                  const res = await apiFetch('/player/me/change-password', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ current_password: changePwCurrent, new_password: changePwNew }),
                                  })
                                  if (!res.ok) {
                                    const err = await res.json().catch(() => null)
                                    throw new Error(err?.detail || 'Failed to change password.')
                                  }
                                  setChangePwMsg({ kind: 'info', text: 'Password changed successfully.' })
                                  setChangePwCurrent('')
                                  setChangePwNew('')
                                  setChangePwConfirm('')
                                } catch (e: any) {
                                  setChangePwMsg({ kind: 'error', text: e?.message || 'Failed to change password.' })
                                } finally {
                                  setChangePwBusy(false)
                                }
                              }}
                            >
                              {changePwBusy ? 'Saving…' : 'Update password'}
                            </button>
                            <button
                              className="btn btn-secondary"
                              type="button"
                              disabled={changePwBusy}
                              onClick={() => { setChangePwOpen(false); setChangePwCurrent(''); setChangePwNew(''); setChangePwConfirm(''); setChangePwMsg(null) }}
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </div>

                    {isAdmin ? (
                      <div className="card card-pad account-card">
                        <div style={{ fontWeight: 750, marginBottom: 8 }}>Admin controls</div>
                        <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
                          Toggle admin mode to reveal elevated cleanup tools.
                        </div>
                        <div className="row-wrap" style={{ gap: 8, alignItems: 'center' }}>
                          <div className="account-pill">Status: {adminMode ? 'Enabled' : 'Disabled'}</div>
                          <button className="btn btn-secondary" type="button" onClick={() => handleToggleAdminMode(!adminMode)}>
                            {adminMode ? 'Disable admin mode' : 'Enable admin mode'}
                          </button>
                        </div>
                      </div>
                    ) : null}

                    <div className="card card-pad account-card">
                      <div style={{ fontWeight: 750, marginBottom: 8 }}>Linked accounts</div>
                      <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
                        Link Google, Discord, or Twitch to enable one-click sign-in and account recovery.
                      </div>
                      <div className="account-provider-grid">
                        {providerOptions.map((provider) => {
                          const isLinked = linkedProviderSet.has(provider.id)
                          return (
                            <div key={provider.id} className="account-provider">
                              <div>
                                <div style={{ fontWeight: 650 }}>{provider.label}</div>
                                <div className="muted" style={{ fontSize: 12 }}>{isLinked ? 'Linked' : 'Not linked'}</div>
                              </div>
                              <button className="btn btn-secondary btn-sm" type="button" disabled>
                                {isLinked ? 'Manage' : 'Link'}
                              </button>
                            </div>
                          )
                        })}
                      </div>
                      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                        Best practice: allow unlink only if another sign-in method is available.
                      </div>
                    </div>

                    <div className="card card-pad account-card">
                      <div style={{ fontWeight: 750, marginBottom: 8 }}>Preferences</div>
                      {preferenceEntries.length ? (
                        <div className="account-kv">
                          {preferenceEntries.map(([key, value]) => (
                            <div key={key}>
                              <div className="muted">{key}</div>
                              <div>{typeof value === 'string' ? value : JSON.stringify(value)}</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="muted" style={{ fontSize: 13 }}>
                          No preferences set yet.
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="card card-pad account-card stack">
                    <div style={{ fontWeight: 750 }}>Integrations</div>
                    <div className="muted" style={{ fontSize: 13 }}>
                      The Beyond 20 browser extension relays your D&amp;D Beyond rolls into TavernTails. Only the extension install is required — no additional software needed.
                    </div>
                    <div className="row-wrap">
                      <button className="btn btn-secondary" type="button" onClick={() => setView('beyond20')}>
                        Beyond 20 settings
                      </button>
                    </div>
                  </div>

                  <div className="card card-pad account-card">
                    <div style={{ fontWeight: 750, marginBottom: 8 }}>Block / Report a User</div>
                    <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>
                      Search for a player by name or email, then block or report them.
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="Search by name or email…"
                        value={moderationSearchQuery}
                        onChange={(e) => setModerationSearchQuery(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') performModerationSearch(moderationSearchQuery) }}
                        style={{ flex: 1 }}
                      />
                      <button
                        className="btn btn-secondary btn-sm"
                        type="button"
                        disabled={moderationSearchBusy || moderationSearchQuery.trim().length < 2}
                        onClick={() => performModerationSearch(moderationSearchQuery)}
                      >
                        {moderationSearchBusy ? '…' : 'Search'}
                      </button>
                    </div>
                    {moderationSearchResults.length > 0 && (
                      <div className="stack" style={{ gap: 6 }}>
                        {moderationSearchResults.map((u: any) => (
                          <div key={u.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--tt-border)' }}>
                            <span style={{ fontSize: 14 }}>{u.name || u.username || u.email}</span>
                            <div style={{ display: 'flex', gap: 6 }}>
                              <button
                                className="btn btn-sm btn-secondary"
                                type="button"
                                onClick={() => {
                                  setBlockReportTarget({ id: u.id, name: u.name || u.username || u.email })
                                  setBlockReportMode('report')
                                  setBlockReportModalOpen(true)
                                }}
                              >
                                Report
                              </button>
                              <button
                                className="btn btn-sm btn-danger"
                                type="button"
                                onClick={() => {
                                  setBlockReportTarget({ id: u.id, name: u.name || u.username || u.email })
                                  setBlockReportMode('block')
                                  setBlockReportModalOpen(true)
                                }}
                              >
                                Block
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                   </>
                  )}

                  <details className="account-debug">
                    <summary>Debug profile payload</summary>
                    <pre className="account-json">{JSON.stringify(profile, null, 2)}</pre>
                  </details>
                </>
              )
            })()}
          </section>
        )}

        {view === 'beyond20' && (
          <div className="dashboard-panel" style={{ padding: 24 }}>
            <Beyond20View
              activeSessionId={activeSession}
              identifier={profile?.email || profile?.username || null}
            />
          </div>
        )}
        {view === 'admin' && isAdmin && (
          <div className="dashboard-panel" style={{ padding: 24 }}>
            <AdminPanel onBack={() => setView('home')} />
          </div>
        )}
        {/* Notification drawer overlay */}
        {notificationsOpen && (
          <div className="drawer-overlay" onClick={() => setNotificationsOpen(false)} />
        )}

        {/* Notification slide-out drawer (right side) */}
        <aside className={`notif-drawer ${notificationsOpen ? 'notif-drawer-open' : ''}`} aria-label="Notifications">
          <div className="drawer-header">
            <div className="dashboard-brand">Notifications</div>
            <button className="drawer-close" type="button" onClick={() => setNotificationsOpen(false)} aria-label="Close notifications">✕</button>
          </div>
          <div className="notif-drawer-body">
            <div className="row-wrap" style={{ justifyContent: 'flex-end', marginBottom: 8 }}>
              <button className="btn btn-quiet btn-sm" type="button" onClick={handleMarkAllRead} disabled={!sortedNotifications.length}>
                Mark all read
              </button>
            </div>

            {!sortedNotifications.length ? (
              <div className="notification-empty">No notifications yet.</div>
            ) : (
              <div className="notification-list">
                {sortedNotifications.map((item) => {
                  const isRead = isNotificationRead(item)
                  const isInvite = item.type === 'friend_invite' || item.type === 'campaign_invite'
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`notification-item ${isRead ? '' : 'notification-item--unread'}`}
                      onClick={() => {
                        if (!isRead) {
                          setReadNotificationIds((prev) => (prev.includes(item.id) ? prev : [...prev, item.id]))
                        }
                        if (isInvite) {
                          setNotificationsOpen(false)
                          setAccountSection('invites')
                          navigate('account')
                        }
                      }}
                    >
                      <div className="notification-item-title">
                        {isInvite && <span style={{ marginRight: 6 }}>👥</span>}
                        {item.title}
                      </div>
                      {item.body ? <div className="notification-item-body">{item.body}</div> : null}
                      <div className="notification-item-time">
                        {item.createdAt ? new Date(item.createdAt).toLocaleString() : 'Just now'}
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </aside>
        <Modal
          open={showCreateModal}
          title="Create Campaign"
          onClose={() => {
            if (createCampaignBusy) return
            setShowCreateModal(false)
            setNewCampaignName('')
            setNewCampaignDescription('')
            setNewCampaignGenre('fantasy')
            setNewCampaignTone('balanced')
            setNewCampaignPacing('moderate')
            setNewCampaignContentRating('pg-13')
            setCreateCampaignError(null)
          }}
        >
          {createCampaignError ? (
            <div className="inline-alert inline-alert-error" style={{ marginBottom: 10 }}>
              {createCampaignError}
            </div>
          ) : null}

          <div className="stack" style={{ gap: 10 }}>
            <div>
              <label className="muted" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Campaign Name <span style={{ color: 'var(--tt-accent, #c084fc)' }}>*</span></label>
              <input
                className="input"
                placeholder="Campaign name"
                value={newCampaignName}
                onChange={(e) => setNewCampaignName(e.target.value)}
                disabled={createCampaignBusy}
                autoFocus
              />
            </div>
            <div>
              <label className="muted" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Description</label>
              <textarea
                className="input"
                placeholder="Description (optional)"
                value={newCampaignDescription}
                onChange={(e) => setNewCampaignDescription(e.target.value)}
                disabled={createCampaignBusy}
                rows={2}
              />
            </div>

            <div className="row-wrap" style={{ gap: 8 }}>
              <div style={{ flex: 1 }}>
                <label className="muted" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Genre <span style={{ color: 'var(--tt-accent, #c084fc)' }}>*</span></label>
                <select className="input" value={newCampaignGenre} onChange={(e) => setNewCampaignGenre(e.target.value)} disabled={createCampaignBusy}>
                  <option value="fantasy">Fantasy</option>
                  <option value="sci-fi">Sci-Fi</option>
                  <option value="horror">Horror</option>
                  <option value="western">Western</option>
                  <option value="steampunk">Steampunk</option>
                  <option value="modern">Modern</option>
                  <option value="post-apocalyptic">Post-Apocalyptic</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label className="muted" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Tone <span style={{ color: 'var(--tt-accent, #c084fc)' }}>*</span></label>
                <select className="input" value={newCampaignTone} onChange={(e) => setNewCampaignTone(e.target.value)} disabled={createCampaignBusy}>
                  <option value="heroic">Heroic</option>
                  <option value="grim">Grim</option>
                  <option value="dark-fantasy">Dark Fantasy</option>
                  <option value="comedy">Comedy</option>
                  <option value="horror">Horror</option>
                  <option value="balanced">Balanced</option>
                </select>
              </div>
            </div>

            <div className="row-wrap" style={{ gap: 8 }}>
              <div style={{ flex: 1 }}>
                <label className="muted" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Pacing <span style={{ color: 'var(--tt-accent, #c084fc)' }}>*</span></label>
                <select className="input" value={newCampaignPacing} onChange={(e) => setNewCampaignPacing(e.target.value)} disabled={createCampaignBusy}>
                  <option value="slow">Slow</option>
                  <option value="moderate">Moderate</option>
                  <option value="fast">Fast</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label className="muted" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Content Rating <span style={{ color: 'var(--tt-accent, #c084fc)' }}>*</span></label>
                <select className="input" value={newCampaignContentRating} onChange={(e) => setNewCampaignContentRating(e.target.value)} disabled={createCampaignBusy}>
                  <option value="family">PG (Family-friendly)</option>
                  <option value="pg-13">PG-13</option>
                  <option value="mature">R (Mature)</option>
                </select>
              </div>
            </div>

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
                    const campaignId = campaign?.id ? String(campaign.id) : null

                    if (campaignId) {
                      // Save initial required settings (genre, tone) and variables (pacing, content_rating)
                      const settingsRes = await apiFetch(`/campaigns/${campaignId}/settings`, {
                        method: 'PUT',
                        body: JSON.stringify({ genre: newCampaignGenre, tone: newCampaignTone }),
                      }).catch(() => null)
                      const varsRes = await apiFetch(`/campaigns/${campaignId}/variables`, {
                        method: 'PUT',
                        body: JSON.stringify({ pacing: newCampaignPacing, content_rating: newCampaignContentRating }),
                      }).catch(() => null)
                      if ((settingsRes && !settingsRes.ok) || (varsRes && !varsRes.ok)) {
                        throw new Error('Campaign created but initial settings could not be saved. You can update them in Settings.')
                      }

                      setActiveCampaignId(campaignId)
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
                    setNewCampaignGenre('fantasy')
                    setNewCampaignTone('balanced')
                    setNewCampaignPacing('moderate')
                    setNewCampaignContentRating('pg-13')
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
                  setNewCampaignGenre('fantasy')
                  setNewCampaignTone('balanced')
                  setNewCampaignPacing('moderate')
                  setNewCampaignContentRating('pg-13')
                  setCreateCampaignError(null)
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </Modal>
        <Modal
          open={showQuickstartSetup}
          title="Start New Game"
          onClose={() => {
            if (quickstartBusy) return
            setShowQuickstartSetup(false)
          }}
        >
          <div className="stack" style={{ gap: 12 }}>
            <div>
              <label className="muted" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Campaign Name <span style={{ color: 'var(--tt-accent, #c084fc)' }}>*</span></label>
              <input
                className="input"
                placeholder="Enter a campaign name"
                value={quickstartCampaignName}
                onChange={(e) => { setQuickstartCampaignName(e.target.value); setQuickstartCampaignNameError(null) }}
                disabled={quickstartBusy}
                autoFocus
              />
              {quickstartCampaignNameError ? (
                <div className="inline-alert inline-alert-error" style={{ marginTop: 6 }}>{quickstartCampaignNameError}</div>
              ) : null}
            </div>

            <div>
              <label className="muted" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Character</label>
              {characters.length > 0 ? (
                <select
                  className="input"
                  value={quickstartSelectedCharId}
                  onChange={(e) => setQuickstartSelectedCharId(e.target.value)}
                  disabled={quickstartBusy}
                >
                  {characters.map((c: any) => (
                    <option key={String(c.id)} value={String(c.id)}>
                      {c.name || 'Unnamed'}{c.class_name ? ` (${c.class_name})` : ''}
                    </option>
                  ))}
                  <option value="__import__">⬆ Import Character</option>
                  <option value="__new__">✚ Create New Character</option>
                </select>
              ) : (
                <select
                  className="input"
                  value={quickstartSelectedCharId}
                  onChange={(e) => setQuickstartSelectedCharId(e.target.value)}
                  disabled={quickstartBusy}
                >
                  <option value="__none__">No character (demo character will be used)</option>
                  <option value="__import__">⬆ Import Character</option>
                  <option value="__new__">✚ Create New Character</option>
                </select>
              )}
            </div>

            <div className="row-wrap" style={{ justifyContent: 'flex-end', gap: 8 }}>
              <button
                className="btn btn-secondary"
                type="button"
                disabled={quickstartBusy}
                onClick={() => setShowQuickstartSetup(false)}
              >
                Cancel
              </button>
              <button
                className="btn"
                type="button"
                disabled={quickstartBusy}
                onClick={async () => {
                  const name = quickstartCampaignName.trim()
                  if (!name) {
                    setQuickstartCampaignNameError('Campaign name is required.')
                    return
                  }
                  if (quickstartSelectedCharId === '__import__') {
                    setShowQuickstartSetup(false)
                    setCharacterCreateOrigin('gameplay')
                    setView('import-character')
                    return
                  }
                  if (quickstartSelectedCharId === '__new__') {
                    setShowQuickstartSetup(false)
                    setCharacterCreateOrigin('gameplay')
                    setView('create-character')
                    return
                  }
                  const charId = quickstartSelectedCharId && quickstartSelectedCharId !== '__none__'
                    ? Number(quickstartSelectedCharId)
                    : null
                  setShowQuickstartSetup(false)
                  await quickstartPlaytest({ campaignName: name, charId })
                  setView('gameplay')
                }}
              >
                {quickstartBusy ? 'Starting…' : 'Start'}
              </button>
            </div>
          </div>
        </Modal>
      </main>
    </div>
  );
};

export default LoggedInDashboard;