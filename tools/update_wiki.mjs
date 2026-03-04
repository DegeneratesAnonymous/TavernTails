/**
 * update_wiki.mjs
 *
 * Generates (or refreshes) one wiki page per TavernTAIls app screen and a
 * Home.md table-of-contents page.  Screenshots are referenced via raw
 * GitHub content URLs so they always reflect the latest commit on main.
 *
 * Usage (called by the screenshot-update workflow):
 *   node tools/update_wiki.mjs <wiki-checkout-dir>
 *
 * Arguments:
 *   <wiki-checkout-dir>  Path to a local checkout of the .wiki.git repo.
 *                        Defaults to "wiki" relative to the repo root.
 *
 * The script only writes files – committing and pushing is left to the
 * calling workflow so git identity and credentials are managed in one place.
 */

import { writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const WIKI_DIR = resolve(process.argv[2] ?? resolve(__dirname, '..', 'wiki'));
const RAW_BASE =
  'https://raw.githubusercontent.com/DegeneratesAnonymous/TavernTails/main/docs/screenshots';

// ---------------------------------------------------------------------------
// Page catalogue
// Each entry describes one app screen.
// ---------------------------------------------------------------------------
const PAGES = [
  {
    file: 'Page-Landing.md',
    title: 'Landing Page',
    screenshot: '01-landing.png',
    description: `The public home page — the first thing any visitor sees before signing in.

## Hero Section

The headline ("Story-first AI GM, built for real tables") captures the product pitch.
The sub-copy explains the three core value propositions: import characters, spin up
campaigns, and keep the session moving with narrative cues, dice prompts, and live
recap support.

Two prominent call-to-action buttons sit in the hero:

| Button | Destination |
|---|---|
| **Sign In** | Login form |
| **Create Account** | Sign-up form |

## Quick-Action Tiles

Below the hero, six shortcut tiles let returning users jump directly to the most
common tasks without signing in first (each tile redirects to the login/sign-up
flow when clicked unauthenticated):

| Tile | Icon | Description |
|---|---|---|
| **Start New Game** | ⚔️ | Create a new campaign and begin your adventure |
| **Load a Game** | 📖 | Continue from one of your existing campaigns |
| **Manage Characters** | 🧙 | View, create, and import your character roster |
| **Manage Campaigns** | 🗺️ | Configure campaigns, players, and documents |
| **Explore** | 🔭 | Browse lore and world details discovered in your campaigns |
| **Guides** | 📜 | Best practices and help for all TavernTAIls tools |

## Background

A decorative dark fantasy background image reinforces the TTRPG theme.
The page has no login gate — it is fully public and optimised for first-time
visitors and organic search landing pages.`,
  },
  {
    file: 'Page-Login.md',
    title: 'Login',
    screenshot: '02-login.png',
    description: `The sign-in form — accessible from the **Sign In** button on the landing page
or any unauthenticated quick-action tile.

## Fields

| Field | Description |
|---|---|
| **Email** | Registered account email address |
| **Password** | Account password (masked) |

## Actions

- **Sign In** — submits the credentials; on success a JWT access token is stored
  in \`localStorage\` and the user is redirected to the Dashboard.
- **Create account** — switches to the Sign-Up form without a page navigation.

## Dev Shortcut

In local development a **"Use dev login"** button auto-fills
\`test@example.com / secret\` so developers can reach the Dashboard in one click.
The button is hidden in production builds.

## Error Handling

Invalid credentials display a red inline error banner above the form.
Network errors (backend unreachable) surface a user-friendly message rather than
a raw HTTP status code.

## Email Verification

If an account exists but the email has not been verified, the login response
includes a verification prompt.  A token input field appears inline so the user
can paste the emailed code without leaving the page.`,
  },
  {
    file: 'Page-Sign-Up.md',
    title: 'Sign Up',
    screenshot: '03-signup.png',
    description: `The account registration form — accessible from **Create Account** on the
landing page or the toggle link on the Login form.

## Fields

| Field | Notes |
|---|---|
| **Username** | Optional unique handle; used in multiplayer sessions |
| **Email** | Must be a valid address; used for login and notifications |
| **Password** | Minimum 8 characters recommended |

## Registration Flow

1. Submit the form — the backend creates a new \`player\` account and sends a
   verification email.
2. A verification code prompt appears inline (no page redirect).
3. Paste the six-digit code; on success the account is marked verified and a JWT
   is issued.
4. The user is immediately redirected to the Dashboard.

**Dev mode:** both email verification and the credential step are bypassed
automatically when \`TAVERNTAILS_SEED_DEV_USER=1\` is set on the backend.

## Validation

Client-side validation checks for a valid email format before submission.
Duplicate-email errors are surfaced inline from the API response.`,
  },
  {
    file: 'Page-Dashboard.md',
    title: 'Dashboard',
    screenshot: '04-dashboard.png',
    description: `The authenticated home screen — shown immediately after a successful login.

## Layout

The Dashboard uses a shell layout with three persistent UI regions:

| Region | Contents |
|---|---|
| **Top bar** | TavernTAIls brand, notification bell (🔔), account button (👤) |
| **Slide-out drawer** | Navigation links to all major views; triggered by the ☰ hamburger icon |
| **Main content area** | Changes based on the selected view |

## Dashboard Home Content

When the \`home\` view is active, the main area greets the user by display name
("Welcome, \${name}") and presents six quick-action tiles:

| Tile | Destination View |
|---|---|
| **Start New Game** | Campaign creation / quickstart flow |
| **Load a Game** | Active session or campaign picker |
| **Manage Characters** | Character roster |
| **Manage Campaigns** | Campaign list |
| **Explore** | Campaign lore browser |
| **Guides** | Built-in help articles |

## Navigation Drawer

Click the hamburger icon (☰ — top-left) to open the slide-out drawer. It
contains labelled buttons for every top-level view:

- Home · Manage Campaigns · Manage Characters · Documents · Explore · Guides
- **Admin** (visible only to admin accounts)

Click any item or tap the overlay to close the drawer.

## Notification Bell

The 🔔 icon in the top-right shows a red badge when there are unread
notifications (campaign invites, friend requests, direct messages).  Clicking it
opens the notification panel (see [[Account|Page-Account]]).

## Account Button

The 👤 icon navigates directly to the [[Account Settings|Page-Account]] view.`,
  },
  {
    file: 'Page-Characters.md',
    title: 'Characters',
    screenshot: '05-characters.png',
    description: `Your full character roster — accessible from the navigation drawer or the
**Manage Characters** quick-action tile.

## Character Cards

Each character is displayed as a card showing:

- **Name** and class/system label
- Core stats summary (HP, level, key attributes)
- Action buttons: **View Sheet**, **Settings**, **Delete**

Selecting a character's card makes it the active character for the current
session.

## Creating a Character

| Path | Description |
|---|---|
| **Create Character** button | Opens the character creation form; enter name, class, and level |
| **Import** button | Opens the [[Import Character|Page-Import-Character]] wizard |

## Character Sheet Modal

Clicking **View Sheet** on any character card opens a full-screen character sheet
modal with tabs:

| Tab | Contents |
|---|---|
| **Summary** | Core stats, saves, skills, HP, currency, class resources |
| **Spells** | Spell slots, prepared spells, spell attack/save DC |
| **Features** | Class features, traits, special abilities |
| **Inventory** | Equipment list with weight and encumbrance |
| **Journal** | Per-character notes and session logs |

## Empty State

If no characters exist, an empty-state card guides the user to either create or
import their first character.`,
  },
  {
    file: 'Page-Import-Character.md',
    title: 'Import Character',
    screenshot: '06-import-character.png',
    description: `The character import wizard — accessible from the **Import** button on the
Manage Characters page or the navigation drawer.

## Import Methods

| Method | Description |
|---|---|
| **PDF Upload** | Upload a PDF character sheet exported from your VTT or character builder |
| **D&D Beyond / Beyond 20** | Relay rolls and character data via the Beyond 20 browser extension |

## Supported Systems

The importer auto-detects the TTRPG system from the uploaded PDF and extracts
all relevant fields:

| System | Fields Extracted |
|---|---|
| **D&D 5e** | Race, class, level, ability scores, saves, skills, HP, spell slots, inventory, currency, features |
| **Pathfinder 2e / 1e** | Class, ancestry, heritage, attributes, proficiencies, feats |
| **Shadowrun 6e** | Metatype, attributes (BOD/AGI/REA/STR/WIL/LOG/INT/CHA/EDG/MAG/RES), essence, skills, qualities, cyberware, nuyen |
| **Alien RPG** | Career, attributes, skills, health/stress, buddy, rival, agenda |
| **Warhammer Fantasy Roleplay 4e** | Career, characteristics, wounds, fate, resilience, skills, talents, trappings |
| **Shadow of the Demon Lord** | Corruption, healing rate, insanity, speed, fortune dice, paths, professions, background |
| **Call of Cthulhu 7e** | Characteristics, magic points, sanity, luck |
| **Starfinder** | Race, theme, homeworld, stamina, resolve, KAC, EAC, initiative, credits, augmentations |
| **Star Trek Adventures** | Attributes, disciplines, focuses, values, determination |

## After Import

Once the system parses the PDF, a preview of the extracted fields is displayed.
Confirm the import to save the character to your roster, or go back to try a
different file.`,
  },
  {
    file: 'Page-Manage-Campaigns.md',
    title: 'Manage Campaigns',
    screenshot: '07-campaigns.png',
    description: `A list of every campaign you own or have joined as a player — accessible from
the navigation drawer or the **Manage Campaigns** quick-action tile.

## Campaign Cards

Each campaign entry shows:

- Campaign **name** and **description**
- **Status** badge (Active / Archived)
- Session count and last-played date
- Action buttons: **Start Session**, **Settings** (host only), **Delete** (host only)

## Creating a Campaign

Click the **New Campaign** button (＋) to open the [[New Campaign|Page-New-Campaign]]
creation modal.

## Joining a Campaign

Players join via an invite link or code shared by the campaign host.  Joined
campaigns appear alongside owned campaigns in this list.

## Empty State

When no campaigns exist, a prompt guides you to create your first campaign or
enter an invite code from a friend.`,
  },
  {
    file: 'Page-New-Campaign.md',
    title: 'New Campaign',
    screenshot: '08-new-campaign.png',
    description: `The campaign creation modal — opened from the **New Campaign** (＋) button on
the Manage Campaigns page.

## Fields

| Field | Description |
|---|---|
| **Campaign Name** | Required; shown to all players in the campaign |
| **Description** | Optional flavour text describing the campaign premise |
| **Genre** | Fantasy · Sci-Fi · Horror · Mystery · Western · Post-Apocalyptic |
| **Tone** | Heroic · Balanced · Grim · Dark Fantasy · Comedic |
| **Pacing** | Slow Burn · Moderate · Fast-Paced · Episodic |
| **Content Rating** | All Ages · PG · PG-13 · Mature |

## After Creation

Clicking **Create** saves the campaign and immediately redirects to
[[Campaign Settings|Page-Campaign-Settings]] where you can fine-tune the
narrative configuration before starting the first session.

## Quickstart Mode

Alternatively, the **Start New Game** tile on the Dashboard home triggers a
condensed quickstart flow that combines campaign creation and session start in a
single step — useful for one-shots or first-time users.`,
  },
  {
    file: 'Page-Campaign-Settings.md',
    title: 'Campaign Settings',
    screenshot: '09-campaign-settings.png',
    description: `The host-only configuration panel for an existing campaign — accessible via the
**Settings** (⚙️) button on any campaign card.

> **Host only:** Players see the session view directly; only the campaign host
> can access this panel.

## Configuration Sections

### World & Story
| Setting | Description |
|---|---|
| **World Name** | The name of the campaign world or setting |
| **Setting Summary** | A paragraph description the AI uses as scene context |
| **Genre** | Fantasy / Sci-Fi / Horror / Mystery / Western / Post-Apocalyptic |
| **Tone** | Heroic / Balanced / Grim / Dark Fantasy / Comedic |

### Rules
| Setting | Description |
|---|---|
| **Ruleset** | D&D 5e / Pathfinder 2e / Shadowrun 6e / Alien RPG / WFRP 4e / Custom |
| **Starting Level** | Character level at the start of the campaign |

### Narrative Variables
| Setting | Description |
|---|---|
| **Pacing** | Slow Burn / Moderate / Fast-Paced / Episodic |
| **Narrative Style** | Descriptive / Cinematic / Minimalist |
| **Naming Style Hint** | Influences NPC and location name generation |
| **Recurring Themes** | Themes the AI weaves into narration (e.g. "betrayal", "redemption") |
| **Content Rating** | All Ages / PG / PG-13 / Mature |

### House Rules
A free-text field for custom rules the AI agents must follow during narration
and scene resolution (e.g. "critical failures always have narrative consequences").

### Game Master
| Option | Effect |
|---|---|
| **AI GM** | AI agents handle all narration, dice prompts, and NPC management |
| **Human GM (player)** | Assigns a specific player as GM; AI shifts to notes + NPC tracking only |

### Player-Run Mode
Toggle to disable all AI narration while keeping automated dice rolls, session
notes, and NPC index.  Useful for traditional tabletop groups that want
TavernTAIls purely as a digital organiser.

## Players & Invites
The **Players** section lists current campaign members and includes an invite
link generator so the host can invite friends.`,
  },
  {
    file: 'Page-Gameplay.md',
    title: 'Gameplay / Session View',
    screenshot: '10-gameplay.png',
    description: `The main play screen — where the actual game session happens.  Reached by
clicking **Start Session** on any campaign card.

## Layout Overview

The session view is a split-panel layout:

### Left Panel — Scene Stage
- **Scene image** — AI-generated artwork for the current scene (when the Image
  agent is enabled; falls back to a placeholder if disabled or unavailable).
- **Scene title** — displayed prominently so all players know where in the story
  they are.
- **Continue button** (header) — advances the AI narrative to the next beat.

### Right Panel — Tools

| Tab | Purpose |
|---|---|
| **Chat** | Real-time chat for all session participants. Type narrative actions, dialogue, or commands. Dice roll syntax (e.g. \`1d20+5\`, \`2d6\`) is detected automatically and roll results are posted inline. Type \`!notes\` to request a session recap. |
| **Character** | Full interactive character sheet (same content as the [[Character Sheet Modal|Page-Characters]]). Stats, spells, features, and inventory are always one click away without leaving the session. |
| **Journal** | Auto-generated session notes plus any manually added entries. The Notes Agent adds key events, NPC encounters, and plot beats automatically. |

## Additional Controls

| Control | Location | Description |
|---|---|---|
| **NPC Index** | Header button | View a snapshot of all NPCs tracked in this session |
| **Documents** | Header button | Access campaign reference PDFs during the session |
| **Image Gallery** | Header button | Browse all AI-generated scene images from the session |
| **Pinned Messages** | Pin icon on messages | Pin important messages (key clues, rules rulings) to a persistent bar at the top of chat |
| **Invite Players** | Invite button | Share a join link so additional players can enter the session |

## Dice Rolling

Dice expressions entered anywhere in the chat input are rolled server-side for
fairness and the full formula + result is posted as a special roll message.
Beyond 20 users can also roll from their D&D Beyond character sheet and have
results relayed automatically (see [[Beyond 20|Page-Beyond20]]).

## AI Agents Active in Session

| Agent | Responsibility |
|---|---|
| **Narrative Agent** | Scene narration, NPC dialogue, story advancement |
| **Scene Analysis Agent** | Detects when dice rolls are needed; prompts players |
| **NPC/Enemy Manager** | Tracks NPC stats, motivations, and combat initiative |
| **Notes Agent** | Logs events; responds to \`!notes\` requests |
| **Image Generation Agent** | Creates scene artwork (requires API key configuration) |`,
  },
  {
    file: 'Page-Documents.md',
    title: 'Documents',
    screenshot: '11-documents.png',
    description: `The document library — accessible from **Documents** in the navigation drawer.

TavernTAIls lets you upload reference PDFs and other files that the AI agents
consult during gameplay, keeping world-building and rules information close at hand.

## Reusable Library

Upload files that can be attached to any campaign.  Typical uploads include:

- Rulebook PDFs (core rules, supplements, monster manuals)
- Homebrew content (custom races, classes, spells, items)
- World lore (history documents, maps, faction guides)
- Random tables (encounter tables, weather charts, treasure lists)

**Supported file types:** PDF, TXT, Markdown (.md), JSON, DOC/DOCX, XLSX, CSV, HTML

Click **Upload Document** to open the system file picker; multiple files can be
selected at once.

## Campaign Documents

If you have created campaigns, each campaign has its own document section showing
documents already attached to it.  Click **View Docs** next to any campaign to
open that campaign's session view with the Documents panel pre-opened.

## Character Documents

Any documents associated with individual characters are listed in this section
(e.g. character backstory PDFs, custom equipment lists).

## How Documents Affect Gameplay

When a session is running, the Narrative and Scene Analysis agents can search
uploaded documents to:

- Answer rules questions without leaving the session
- Generate encounters consistent with your custom monsters or locations
- Reference lore details when narrating scenes in your homebrew world`,
  },
  {
    file: 'Page-Explore.md',
    title: 'Explore',
    screenshot: '12-explore.png',
    description: `The lore browser — accessible from **Explore** in the navigation drawer or
the **Explore** quick-action tile on the Dashboard.

## Purpose

As you play through campaigns, TavernTAIls automatically catalogues discovered
lore: location descriptions, NPC profiles, faction histories, and world details
that emerge during sessions.  The Explore view is the persistent reference for
everything your characters have uncovered.

## Campaign Lore

Select any of your campaigns to browse its collected lore entries.  Each entry
is tagged with the session where it was discovered so you can trace back the
context.

### Lore Categories (populated as you play)

| Category | Description |
|---|---|
| **Locations** | Places visited or mentioned during sessions |
| **NPCs** | Non-player characters encountered, with their descriptions and motivations |
| **Factions** | Organisations, guilds, and groups the party has interacted with |
| **Events** | Major plot events and world-changing moments |
| **Items** | Notable artefacts, magic items, and plot-relevant equipment |

## Empty State

A new account with no campaigns will see a prompt to start a campaign and begin
discovering lore.  Once sessions are underway, entries are added automatically
by the Notes and NPC agents.`,
  },
  {
    file: 'Page-Guides.md',
    title: 'Guides',
    screenshot: '13-guides.png',
    description: `Built-in help articles — accessible from **Guides** in the navigation drawer or
the **Guides** quick-action tile on the Dashboard.

The Guides view provides concise how-to cards covering the most common tasks and
concepts in TavernTAIls.

## Guide Articles

| Article | Summary |
|---|---|
| **Getting Started** | Create a campaign, import or create a character, then start your first session. Step-by-step walkthrough for new users. |
| **Importing Characters** | Upload a PDF character sheet to import your existing character. Covers the Beyond 20 extension for live D&D Beyond roll relay. |
| **AI Game Master** | How the AI GM agents work: scene narration, dice prompts, NPC tracking. How to assign an AI vs human GM in campaign settings. |
| **Managing Documents** | Upload campaign PDFs, rule sets, or random tables under Documents to give the AI context during gameplay. |
| **Player-Run Mode** | Enable player-run mode when a human GM is running the session. AI continues to handle notes and NPC tracking automatically. |

## Getting Help

If these guides don't answer your question, use the **Contact** option in Account
Settings to submit a support ticket.`,
  },
  {
    file: 'Page-Account.md',
    title: 'Account Settings',
    screenshot: '14-account.png',
    description: `The account management view — accessible by clicking the **👤** icon in the
top-right corner of the top bar.

## Tabs

The Account view is divided into three tabs:

| Tab | Contents |
|---|---|
| **Profile** | Personal details, security settings, friends list, linked OAuth providers, integrations, and moderation tools |
| **📨 Inbox** | Direct messages between friends and campaign invites |
| **🎫 My Issues** | Support tickets you have submitted |

---

## Profile Tab

### Identity Card
Shows your display name, email, username, user ID, verification status, and
account creation date.  Click **Edit Profile** to update your display name,
username, or email address in-line.

### Friends
Displays your friend count and a preview of up to three friends.  Friends can
be sent direct messages via the Inbox tab and invited to campaigns.

### Linked Accounts
Link or unlink OAuth providers (Google, Discord, Twitch) to enable social login
and single sign-on alongside your email/password credentials.

### Security
Change password and view active sessions.

### Preferences
Key-value display of any stored account preferences (theme, notification
settings, etc.).

### Integrations
Shows the Beyond 20 browser extension integration status and provides a
shortcut to the [[Beyond 20 Settings|Page-Beyond20]] page.

### Block / Report a User
Search for a player by name or email and block them (hides their messages) or
file a report for moderation review.

---

## Inbox Tab

The Inbox shows received direct messages from friends and pending campaign
invites.  Three sub-tabs are available:

| Sub-tab | Description |
|---|---|
| **Inbox** | Received messages; unread count shown in the tab badge |
| **Sent** | Messages you have sent to friends |
| **Compose** | Write and send a new direct message to a friend |

---

## My Issues Tab

Lists every support ticket you have submitted, showing the subject, current
status badge, and timestamps.  Click **Contact** to open the contact form and
submit a new ticket.

### Ticket Statuses
| Status | Meaning |
|---|---|
| **Open** | Ticket received; awaiting triage |
| **In Progress** | Being investigated by the support team |
| **Resolved** | Issue has been fixed or answered |
| **Closed** | No further action required |`,
  },
  {
    file: 'Page-Beyond20.md',
    title: 'Beyond 20',
    screenshot: '15-beyond20.png',
    description: `The Beyond 20 integration settings page — accessible from the
**Beyond 20 settings** button in the [[Account|Page-Account]] view under Integrations.

## What is Beyond 20?

[Beyond 20](https://beyond20.here-for-more.info/) is a free, open-source browser
extension for Chrome and Firefox.  Once installed, it detects dice rolls made on
a D&D Beyond character sheet and forwards them in real time into your active
TavernTAIls session chat — no copy-pasting required.

## Installation

| Browser | Link |
|---|---|
| **Chrome / Edge** | [Chrome Web Store](https://chrome.google.com/webstore/detail/beyond-20/gnblbpbepfbfmoobegdogkglpbhcjofh) |
| **Firefox** | [Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/beyond-20/) |

No additional software or server configuration is required beyond the browser
extension itself.

## How It Works

1. Install the extension in your browser.
2. Open your D&D Beyond character sheet.
3. Start a TavernTAIls session (the extension detects the active session
   automatically via the page's identifier).
4. Roll any dice on the D&D Beyond sheet — the result appears instantly in the
   TavernTAIls session chat as a formatted roll message.

## Custom Domain Configuration

If TavernTAIls is hosted on a custom domain (self-hosted or staging), click the
**Beyond 20 settings** button to add the domain to the Beyond 20 allowed-domains
list so the extension knows to relay rolls to that site.  The identifier shown on
this page links your Beyond 20 extension to your specific TavernTAIls account.

## Troubleshooting

- Ensure TavernTAIls is open in the **same browser** as your D&D Beyond sheet.
- Check that the extension has permission to run on both the D&D Beyond and
  TavernTAIls domains.
- Reload both tabs after installing the extension.
- If rolls still do not appear, verify that a session is active in TavernTAIls
  before rolling on D&D Beyond.`,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Render a single page's markdown content.
 */
function renderPage({ title, screenshot, description }) {
  const imgUrl = `${RAW_BASE}/${screenshot}`;
  return [
    `# ${title}`,
    '',
    `> Screenshot auto-updated on every merge to \`main\` via the`,
    `> [screenshot-update](https://github.com/DegeneratesAnonymous/TavernTails/actions/workflows/screenshot-update.yml) workflow.`,
    '',
    `![${title}](${imgUrl})`,
    '',
    description.trim(),
    '',
    '---',
    '',
    '_← Back to [[Home]]_',
    '',
  ].join('\n');
}

/**
 * Render the Home.md table-of-contents page.
 */
function renderHome() {
  const rows = PAGES.map(
    ({ file, title, screenshot }) =>
      `| [[${title}|${file.replace(/\.md$/, '')}]] | ![${title} thumbnail](${RAW_BASE}/${screenshot}) |`,
  );

  return [
    '# TavernTAIls — App Pages',
    '',
    'This wiki documents every screen in TavernTAIls with an auto-updated screenshot.',
    'Screenshots refresh automatically on every merge to `main`.',
    '',
    '## Pages',
    '',
    '| Page | Screenshot |',
    '|---|---|',
    ...rows,
    '',
    '---',
    '',
    '## GitHub Feature Guide',
    '',
    'Beyond the app screens, TavernTAIls uses the following GitHub features:',
    '',
    '| Feature | How we use it |',
    '|---|---|',
    '| **Actions** | CI (lint/test/build), screenshot refresh, wiki update, staging deploy |',
    '| **Container Registry (GHCR)** | Docker image published on every merge to `main` / `develop` |',
    '| **Issue Templates** | Structured bug reports, feature requests, dev-agent tasks |',
    '| **PR Template** | Consistent checklist for every pull request |',
    '| **Labels & Labeler** | Auto-labelled PRs and issues via `.github/labeler.yml` |',
    '| **CODEOWNERS** | Ensures the right reviewers are requested automatically |',
    '| **Dependabot** | Automated weekly dependency-update PRs for npm, pip, and Actions |',
    '| **Discussions** | Community Q&A, ideas, and announcements (enable in repo Settings → Features) |',
    '| **Wiki** | This wiki — per-page docs with live screenshots |',
    '',
  ].join('\n');
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

mkdirSync(WIKI_DIR, { recursive: true });

// Write individual page files
for (const page of PAGES) {
  const dest = resolve(WIKI_DIR, page.file);
  writeFileSync(dest, renderPage(page), 'utf8');
  console.log(`  ✓ ${page.file}`);
}

// Write Home.md
const homeDest = resolve(WIKI_DIR, 'Home.md');
writeFileSync(homeDest, renderHome(), 'utf8');
console.log('  ✓ Home.md');

console.log(`\nWiki pages written to ${WIKI_DIR}`);
