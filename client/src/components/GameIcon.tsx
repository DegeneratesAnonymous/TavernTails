/**
 * GameIcon — maps legacy emoji strings to mono-color Lucide SVG icons.
 *
 * Usage:  <GameIcon emoji={sys.emoji} size={24} />
 *
 * Any emoji without a mapping falls back to <Sparkles /> so the UI never
 * breaks when new emojis are added to wizard-data.
 */
import React from 'react'
import {
  Sword, Swords, Shield, BookOpen, Sparkles, Star, Leaf, Flame, Moon,
  Music, Cross, Pickaxe, Axe, User, Zap, FlaskConical, Wrench, Scale,
  Rocket, Building2, Bot, Cpu, Target, Crosshair, Dumbbell, Eye, Gem,
  Crown, Microscope, Pencil, AlertTriangle, Mail, FolderOpen, Map,
  Search, Clock, SunMoon, Scroll, Wand2, Waves, Ghost, Skull, Globe,
  Theater, Telescope, MessageCircle, PawPrint, Feather,
  type LucideProps,
} from 'lucide-react'

type IconMap = Record<string, React.FC<LucideProps>>

const EMOJI_ICON_MAP: IconMap = {
  // ── Systems ────────────────────────────────────────────────────────────────
  '⚔️': Sword,      // D&D 5e
  '⚔':  Sword,      // without variation selector (CharacterPanel)
  '🗺️': Map,        // Pathfinder 2e
  '🐉': Flame,      // Pathfinder 1e / Dragonborn ancestry
  '🚀': Rocket,     // Starfinder
  '🐙': Waves,      // Call of Cthulhu
  '🖖': Star,       // Star Trek
  '💀': Skull,      // Shadow of the Demon Lord / grim
  '🐺': Axe,        // Warhammer Fantasy
  '🎃': Ghost,      // Alien RPG
  '🌆': Building2,  // Shadowrun
  '⚡': Zap,        // Star Wars Saga / fast pacing
  '🕯️': Flame,     // OSR
  '✨': Sparkles,   // Custom/Homebrew / sorcerer / misc
  // ── Tone / genre / pacing icons ────────────────────────────────────────────
  '🌑': Moon,       // Warlock / grim tone
  '🌘': Moon,       // Slow burn
  '🕵️': Search,    // Thriller
  '👑': Crown,      // Political intrigue
  '🏰': Building2,  // Fantasy genre / dark lord
  '🔍': Search,     // Mystery / Investigator
  '🕰️': Clock,     // Moderate pacing
  '🎭': Theater,    // Comedy / Noble
  // ── Ancestries ─────────────────────────────────────────────────────────────
  '🧑': User,       // Human
  '🧝': User,       // Elf
  '⛏️': Pickaxe,   // Dwarf
  '🌿': Leaf,       // Halfling / Druid
  '🔮': Gem,        // Gnome
  '🌓': SunMoon,    // Half-Elf
  '💪': Dumbbell,   // Half-Orc
  '😈': Zap,        // Tiefling
  '🔥': Flame,      // Goblin
  '🍃': Leaf,       // Leshy
  '🐱': PawPrint,   // Catfolk
  '🐦': Feather,    // Tengu
  '👽': Globe,      // Alien / Other Species
  '🤖': Bot,        // Android / Droid
  // ── Classes ────────────────────────────────────────────────────────────────
  '🔧': Wrench,     // Artificer
  '🪓': Axe,        // Barbarian
  '🎵': Music,      // Bard
  '✝️': Cross,      // Cleric
  '🛡️': Shield,    // Fighter
  '👊': Swords,     // Monk
  '⚜️': Crown,      // Paladin / Champion
  '🏹': Target,     // Ranger
  '🗡️': Swords,    // Rogue
  '📚': BookOpen,   // Wizard class
  '⚗️': FlaskConical, // Alchemist
  '🧙': Wand2,      // Witch / wizard UI icon
  '🌙': Moon,       // Oracle
  '⚖️': Scale,      // Inquisitor
  // ── Star Trek / Starfinder species ─────────────────────────────────────────
  '🌟': Star,       // Trill / hero moment
  '🌠': Star,       // Shirren
  '🌌': Star,       // Galaxy / space
  '🔬': Microscope, // Biohacker / Scientist
  '🦾': Cpu,        // Nanocyte / Mechanic
  '🔭': Telescope,  // Explore / Science
  '🔫': Crosshair,  // Gunslinger / Operative
  // ── UI / admin ─────────────────────────────────────────────────────────────
  '✏️': Pencil,     // Edit / Custom class
  '⚠️': AlertTriangle, // Warning
  '✉️': Mail,       // Email
  '📂': FolderOpen, // Upload folder
  '📖': BookOpen,   // Load a game / documents
  '📜': Scroll,     // Guides
  '👁️': Eye,        // Eye
  '🗣': MessageCircle, // Social
  '🛠': Wrench,    // Utility
}

// Re-export so callers can import individual icons if they want the same style
export { type LucideProps }

export interface GameIconProps extends LucideProps {
  /** An emoji character (or empty string) to look up in the icon map. */
  emoji: string
}

/**
 * Renders the Lucide mono-color SVG that corresponds to the given emoji.
 * Falls back to <Sparkles /> for any unrecognised emoji.
 */
export function GameIcon({ emoji, size = 20, ...rest }: GameIconProps) {
  const key = emoji?.trim() ?? ''
  const Icon: React.FC<LucideProps> = EMOJI_ICON_MAP[key] ?? Sparkles
  return <Icon size={size} {...rest} />
}

export default GameIcon
