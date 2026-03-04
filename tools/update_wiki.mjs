/**
 * update_wiki.mjs
 *
 * Generates (or refreshes) one wiki page per TavernTails app screen and a
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
    description: `The public home page — the first thing any visitor sees.

The headline ("Story-first AI GM, built for real tables") explains the product pitch.
Below it are six shortcut tiles so returning users can jump directly to:

- **Start New Game**
- **Load a Game**
- **Manage Characters**
- **Manage Campaigns**
- **Explore**
- **Guides**

The **Sign In** and **Create Account** buttons in the hero area are the primary
call-to-action for new visitors.`,
  },
  {
    file: 'Page-Login.md',
    title: 'Login',
    screenshot: '02-login.png',
    description: `A minimal login form with **Email** and **Password** fields.

The **Sign up** button takes you to account creation.  In local development a
**"Use dev login"** button auto-fills \`test@example.com / secret\` so you can get
into the app without typing credentials every time.`,
  },
  {
    file: 'Page-Sign-Up.md',
    title: 'Sign Up',
    screenshot: '03-signup.png',
    description: `Account creation form.  Enter a username, email address, and password to register.

After sign-up, email verification is required before full access is granted.
In dev mode both email verification and credential entry are bypassed automatically.`,
  },
  {
    file: 'Page-Dashboard.md',
    title: 'Dashboard',
    screenshot: '04-dashboard.png',
    description: `The authenticated home screen.  Greets you by name ("Welcome, tester") and
presents the same six quick-action tiles as the landing page, but now scoped to
your account data:

| Tile | What it does |
|---|---|
| **Start New Game** | Create a fresh campaign and jump into your adventure. |
| **Load a Game** | Continue from one of your existing campaigns. |
| **Manage Characters** | View, create, and import characters. |
| **Manage Campaigns** | Configure campaigns, players, and documents. |
| **Explore** | Browse lore and world details discovered in your campaigns. |
| **Guides** | Best practices and help for all TavernTAIls tools. |`,
  },
  {
    file: 'Page-Characters.md',
    title: 'Characters',
    screenshot: '05-characters.png',
    description: `Your character roster.  The page lists every character attached to your account
with options to **Create Character** (build from scratch) or **Import** (from a
JSON export or D&D Beyond link).

When you have characters, each card shows the character's key stats and lets you
select one as the active character for an upcoming session.`,
  },
  {
    file: 'Page-Import-Character.md',
    title: 'Import Character',
    screenshot: '06-import-character.png',
    description: `The character import wizard.

Paste in a D&D Beyond character URL or upload a JSON export from your preferred
VTT or character builder.  TavernTAIls parses the data and creates a local
character record that stays in sync with the campaign.

**Supported systems include:** D&D 5e, Pathfinder 2e, Shadowrun 6e, Alien RPG,
Warhammer Fantasy Roleplay 4e, Shadow of the Demon Lord, Call of Cthulhu 7e,
and Starfinder.`,
  },
  {
    file: 'Page-Manage-Campaigns.md',
    title: 'Manage Campaigns',
    screenshot: '07-campaigns.png',
    description: `A list of every campaign you own or have joined.

Each entry shows the campaign name, its current status, and quick links to open
or configure it.  The **New Campaign** button starts the creation flow.`,
  },
  {
    file: 'Page-New-Campaign.md',
    title: 'New Campaign',
    screenshot: '08-new-campaign.png',
    description: `The campaign creation form.

Give your campaign a name and description, choose an initial setting, and
optionally attach reference documents (rule books, homebrew PDFs, world lore).
Once saved, you're taken to Campaign Settings to finish configuration before
the first session.`,
  },
  {
    file: 'Page-Campaign-Settings.md',
    title: 'Campaign Settings',
    screenshot: '09-campaign-settings.png',
    description: `The host-only configuration panel for an existing campaign.

| Section | Options |
|---|---|
| **World & Story** | World name, setting summary, genre (Fantasy / Sci-Fi / Horror…), tone (Heroic / Grim / Dark Fantasy…) |
| **Rules** | Ruleset (D&D 5e, Pathfinder 2e, Shadowrun…), starting character level |
| **Narrative Variables** | Pacing, narrative style, naming style hint, recurring themes, content rating |
| **House Rules** | Free-text rules the AI agents must respect |
| **Game Master** | Assign AI as GM or designate a player (AI shifts to note-taking mode) |
| **Player-run Mode** | Toggle to disable all AI narration while keeping dice rolls, notes, and NPC tracking |

Only the campaign host sees this panel — players are directed to the session view.`,
  },
  {
    file: 'Page-Gameplay.md',
    title: 'Gameplay / Session View',
    screenshot: '10-gameplay.png',
    description: `The main play screen — where the actual game happens.

The layout is split into two panels:

**Left panel — Scene area**
- Displays the current scene image (AI-generated when the Image agent is active).
- Shows the scene title so everyone knows where in the story they are.
- The **Continue** button in the header advances the narrative when using AI.

**Right panel — Tools**

| Tab | Purpose |
|---|---|
| **Chat** | Type messages, commands, or dice rolls like \`1d20+3\` and press **Send**. Roll results are logged inline. Type \`!notes\` for a session recap. |
| **Character** | Your full character sheet, always one click away without leaving the session. |
| **Journal** | Auto-generated and manually added session notes so nothing gets lost. |`,
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
