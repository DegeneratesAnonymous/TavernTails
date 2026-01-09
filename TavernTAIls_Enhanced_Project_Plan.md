TavernTAIls Unified Project Plan

STATUS NOTE (2026-01-08)
- The current single source of truth for roadmap + acceptance criteria is `PROJECT_PLAN.md`.
- This document is retained as a long-form reference/brain-dump and may lag implementation.
- When updating scope/status, update `PROJECT_PLAN.md`, `MVP_DELIVERY_CHECKLIST.md`, and `PROGRESS.md` first.

Purpose: This document serves as the comprehensive technical and product plan for TavernTAIls, an AIassisted solo or co-op tabletop RPG platform. It combines the high-level vision and architecture with
detailed work packages and deliverables. The goal is to guide development in a modular, efficient way—
especially leveraging AI coding assistants—while ensuring a robust, scalable, and enjoyable platform for
players.
Vision & Scope
Product Vision: Create a solo-friendly tabletop RPG companion that acts as an AI Game Master,
orchestrating narrative beats, scene mechanics, NPCs, and visual aids so a single player (or small
asynchronous group) can enjoy deep campaign experiences from any device .
Scope & MVP: TavernTAIls will be a lightweight web application where players manage campaigns
powered by modular AI agents. The platform supports persistent world state, player-managed
documents, and both asynchronous “play-by-post” style sessions and live play. The MVP will focus on
core functionality: user accounts & authentication, campaign creation and management, session
document handling (Core/Flavor/Hidden types), character creation/import, an invite & membership
system, basic AI agent stubs (for narrative control, scene analysis, NPC management, and notes), a
dice rolling engine, chat/turn management, and a developer-friendly startup script. Integrations and
advanced agent logic are planned for post-MVP phases (Phase 1/2).
Solo & Asynchronous Play: A key design goal is that a single player can experience a full campaign
without a human Game Master. The AI agents collaboratively fill the GM role. The system also
supports asynchronous multiplayer: players in different time windows can take turns, with the
platform providing persistent chat logs and notifications to coordinate gameplay. This ensures
flexibility for co-op play without requiring everyone to be online simultaneously.
Core Pillars
Agent-Oriented Gameplay: Dedicated backend and frontend agents handle distinct aspects of
gameplay (Narrative storytelling, Scene analysis, NPC/Enemy management, Storyboard tracking,
Note-taking, Image generation, etc.). These agents collaborate via well-defined APIs, allowing
modular development and the potential for independent scaling or replacement .
Session-Centric User Experience: All game activity is organized into sessions (within campaigns). A
session encapsulates the story state, active players, associated documents, and ongoing chat. This
bundling allows players to seamlessly resume progress across devices and enables both live and
asynchronous play with persistent state.
Player Identity & Characters: Players have accounts and can create or import RPG characters.
Characters are associated with user profiles, and invites to sessions are tied to characters (the host
can require a minimum character level for entry). Authenticated users manage their characters,
accept invites, and join sessions in-character at the GM-defined level .
Reliability & Automation: Emphasis on a deterministic and automated development and gameplay
experience. For developers, this means a consistent local environment, one-step setup scripts, and
•
1
•
•
1.
2
2.
3.
3
4.
1
automated testing (including playthrough tests and CI checks) . For gameplay, this means
systems (like turn order or dice outcomes) behave predictably, and AI outputs are validated for
coherence and appropriateness by the orchestrating GM agent.
Glossary
Session AI: The collective term for the backend AI agents that generate and manage game content
(narrative, NPC actions, etc.) during a session.
Campaign / Story / Quest: A Campaign is the top-level container for an ongoing game world or
storyline, which can span many sessions. A campaign may contain one overarching Story (plotline)
composed of multiple Quests. Each quest is a self-contained adventure or mission that may play out
over one or more sessions.
Session: A single play instance or meetup within a campaign. In TavernTAIls, a session can be live
(real-time) or asynchronous. Sessions have associated chat logs, active participants, and references
to relevant documents.
Session Documents: The collection of files and documents that define or enrich the game. These
are categorized as Core, Flavor, or Hidden (explained below). Session documents persist within a
campaign and are used by players and AI agents to maintain world state and context.
Session Documents & Knowledge Base
TavernTAIls organizes game-related documents into three categories, with rules for their visibility and use: -
Core Documents: Essential, persistent assets that define the canonical state of the campaign. Examples
include character sheets, the world map, key locations, a party roster, or rule reference documents. Core
documents are typically created and maintained by players/DMs and have versioning for change tracking.
All players in the campaign can view relevant Core documents (e.g. everyone sees the world map or party
roster), and changes are logged for accountability. - Flavor Documents: Optional, player-provided materials
that set the tone or provide extra inspiration. These might be lore backstories, homebrew rules, random
encounter tables, inspirational images, or PDFs of related content. Flavor docs can be uploaded to a
campaign to influence the AI’s creativity or just for player reference. They are not required for play and can
be reused across campaigns. All players can see flavor documents (assuming the uploader shares them),
but these docs don't directly alter core game state. - Hidden Documents: Game master (host)-only
documents containing secret information not revealed to players (unless the host deliberately shares them).
These include the overarching plot outline, NPC secrets, planned encounters, puzzle solutions, and any
information meant to be behind-the-scenes. Hidden docs are accessible only via the DM interface and
require appropriate permissions. Access to these is audited so that any viewing or editing is logged,
preventing abuse.
Storage & Access: In the MVP implementation, documents will be stored on the server’s filesystem in a
campaign-specific directory structure (e.g. data/campaigns/{campaign_id}/documents/ ). Each stored
document has metadata in the database including an ID, filename, uploader, category (Core/Flavor/Hidden),
visibility permissions, tags, a checksum, and potentially an embedding vector for semantic search. In a
production deployment, this can be swapped for a cloud storage backend (S3 or S3-compatible) with
minimal changes, allowing scalable storage of large media files. Core documents will support simple
versioning (e.g. storing past revisions or maintaining a version number) so that changes over time can be
tracked and rolled back if needed. This version history, combined with metadata and audit logs, forms a
2
•
•
•
•
2
knowledge base that the Session AI agents can query to remember past events and maintain consistency in
the narrative.
Metadata & Semantic Search: Optionally, when a document is added or updated, the system can generate an
embedding (vector representation) of its content and store it in a vector index (using an extension like
Postgres pgvector or an in-memory vector store). This enables semantic searches – for example, an agent
could find relevant lore in flavor documents or recall a past event from player notes by similarity search,
improving the AI’s memory beyond the session transcript. For cost and simplicity, semantic search is a
Phase 2 feature; initial implementations may rely on direct keyword search or use simple embeddings with
open-source models. Per-campaign (or per-user) indexing ensures data privacy (an AI will not accidentally
retrieve another campaign’s lore).
System Architecture
Overview: TavernTAIls is built as a classic web application with a React frontend and a Python (FastAPI)
backend, augmented by background workers for AI tasks and a database for persistence. The design
emphasizes modularity—each functional area (agents, chat, characters, etc.) is relatively decoupled—so that
development can proceed in parallel and components can be easily maintained or replaced.
Backend (FastAPI): The backend is implemented in FastAPI (Python 3.x), using SQLModel (built on
SQLAlchemy) for ORM and data models. The server is organized into modular routers/endpoints,
often grouped by feature or agent (e.g. under server/agents/ there may be submodules for
player, campaign, narrative, scene, etc.). This separation aligns with the agent-oriented design and
helps keep the codebase modular. The backend uses JWT tokens for authentication (via a module
server/auth.py ) and includes middleware for things like CORS and error handling. For
development and testing, a lightweight SQLite database is used, while production will use
PostgreSQL (with migration support via Alembic) . File storage for documents is local (as
described above) but abstracted so it can later point to cloud storage. The backend exposes both
RESTful APIs and WebSocket endpoints (for real-time features).
Frontend (React): The frontend is a single-page application built with React and TypeScript (Create
React App). It communicates with the backend via REST and WebSocket. A centralized API utility
module (e.g. src/api.ts ) handles token management and HTTP requests . Key UI elements
include: the Login/Signup pages, a dashboard listing the user’s campaigns, the gameplay interface
(with chat, document viewer, dice roller, etc.), and various modals for creating campaigns, inviting
players, or uploading documents. The UI is designed to be responsive and mobile-friendly,
recognizing that players may use tablets or phones. Ensuring a good experience on smaller screens
is an active priority (e.g. adding CSS breakpoints and touch-friendly controls as noted in current
initiatives).
Real-time Communication: For live sessions and instant updates, TavernTAIls uses WebSockets. The
backend provides an endpoint such as GET /campaigns/{id}/ws that clients can connect to for a
real-time feed of events . This channel is used to broadcast chat messages, narrative updates
from the AI GM, dice roll results, turn notifications, and other events to all participants in a session.
Under the hood, a publish-subscribe mechanism (likely backed by Redis or a similar store) will enable
scaling: if the backend runs on multiple instances or processes, a message published by one should
be received by subscribers on others. In MVP (single-server), a simpler in-memory broadcast or
polling mechanism can be used, but the design anticipates using Redis Pub/Sub or a message
broker for multi-instance scalability. The WebSocket connections will be authenticated (e.g. via JWT at
•
4
•
5
•
6
3
connection) and tied to the user and campaign, so that unauthorized users cannot subscribe to
sessions they aren’t part of.
Background Workers & Task Queue: Heavy operations (especially calls to external AI APIs or image
generation jobs, which can take seconds) are offloaded to background worker processes. The
application will incorporate a task queue system such as Celery or RQ (Redis Queue). For instance,
when an image needs to be generated or a large language model (LLM) agent needs to produce a
chunk of narrative, the request can be enqueued and processed by a worker so that the main thread
is not blocked and the HTTP request can return promptly. Results from workers are then stored (in
the database or a cache) and forwarded to the relevant players via WebSocket once ready .
This design keeps the app responsive and provides built-in retry logic and error handling: if a task
fails (due to an API error or timeout), it can be retried or a fallback result can be used (see Agent
Orchestration below for fallback strategies).
Scalability Considerations: The architecture is cloud-ready. By using stateless web servers (all state
is either in the database, object storage, or Redis), we can run multiple instances behind a load
balancer to handle more users. Session stickiness for WebSockets can be achieved via a routing layer
or using a central pub/sub. The reliance on Postgres means we can scale vertically (bigger instance)
or add read replicas if needed for heavy read traffic. Caching layers (Redis or in-memory caches) can
be introduced for frequently accessed data or expensive queries. For static content and media, using
a CDN or cloud storage with caching will help serve images/documents efficiently to users globally.
We also plan to use Docker for containerization, which makes local development easier and provides
a path to deploy on container orchestration platforms (like Kubernetes) when scaling beyond a
single server. Initially, a simple Docker Compose setup or a single VM deployment will suffice, but the
components (web app, workers, DB, cache) are designed to be separable if needed.
Agents & AI Orchestration
One of TavernTAIls’ distinguishing features is the Session AI: a collection of specialized AI agents each
handling an aspect of game mastering, coordinated by a GM (Game Master) Orchestrator agent. The design
principle is to keep each agent focused and testable, with clearly defined input/output contracts. Agents
may use large language models (LLMs) or other AI/algorithmic techniques internally, but to the rest of the
system they present deterministic, structured interfaces (JSON in/out).
Agent Roles & Responsibilities: (Each agent runs as part of the backend, and has a corresponding frontend
component or UI element if needed for input/output visualization.) - GM Agent (Orchestrator & Quality Gate):
The GM agent acts as the lead orchestrator and “dungeon master.” It does not generate content from
scratch; instead, it requests outputs from other agents (Writer, Narrator, NPC, etc.), validates coherence and
adherence to the campaign’s rules/tone, and then composes the final narrative or decision for the players.
The GM agent ensures the overall quality of the session output, applying any high-level directives (e.g.
narrative style guidelines, safety filters) before content reaches players. It also manages what information is
revealed to players versus what remains hidden. In essence, the GM agent is the “director” that keeps the
other agents’ contributions consistent with each other and with the game state. - Writer (Story Planner)
Agent: Generates long-form story elements, such as the overarching plot of a quest or the next major story
beat. Given the current campaign state, past events, and any story cues (like a quest hook or a recent player
decision), the Writer agent produces narrative outlines or suggestions for what could happen next. Its
output might be something like: “The party reaches the ancient ruins where a hidden guardian awaits and a
puzzle blocks their path.” The GM agent will review this for consistency (ensuring it doesn't conflict with any
established lore in Core docs or past events) and then pass it to the Narrator agent to flesh out details. -
•
7 8
•
4
Narrator Agent: Turns story outlines and player actions into moment-to-moment descriptions. It generates
the actual prose that the players see for each scene, including environmental descriptions, NPC dialogue,
and prompts for player decisions. The Narrator takes into account the current scene context, the characters
present, and the latest player action. For example, if a player says, “I open the door quietly,” the Narrator
agent will produce the outcome description in a storytelling style, e.g. “You ease the door open with a soft
creak. Beyond lies a dark hall where shadows writhe along the walls.” The Narrator may work closely with (or as
a sub-function of) the GM agent to ensure style and tone consistency. - Scene Analysis Agent: Monitors the
evolving scene to identify triggers for game mechanics or rule enforcement. It parses the narrative and
player actions to determine if a dice roll or rule resolution is needed. For example, if a player’s action has a
chance of failure (“sneak past an enemy”), the Scene agent might signal for a stealth check. It also tracks
structured encounters (like combat turn order) and environment effects. When it detects such triggers, it
emits structured events, e.g. a roll request: {type: "roll_request", data: {"formula":
"1d20+Stealth", "character_id": 42}} , which the PencilPusher engine will resolve. Essentially, the
Scene agent ensures that game rules (from the RPG system) are applied within the narrative flow. -
PencilPusher Agent (Dice & Mechanics Engine): Responsible for all dice rolls and mechanical calculations.
This agent (or service) can be invoked directly by the system when a roll is needed (whether triggered by the
Scene agent or a player action). It interprets dice notation (e.g. "2d6+3"), applies character-specific
modifiers from the relevant character sheet (accessible via Core docs or the database), executes the roll
using a secure random generator, and returns the outcome. For combat, it might also handle damage
calculation or success/failure determination if given the target difficulty. The PencilPusher returns
structured results (e.g. {result: 14, breakdown: [4,5]+5} for a 2d6+3 roll), and these results are
then inserted into the narrative (by the GM or Narrator agent) or sent as system messages. All roll results in
a session are logged (to the Roll or Message log) for transparency. - Scribe (Notes) Agent: The Scribe
agent maintains a running log of important information and can provide recaps or summaries. It records
key events, NPC names, discovered clues, loot, and any notable changes to character status. After each
session (or on demand), it can generate a brief summary for the players to review. The Scribe might also
assist players by providing a “notes” command (for example, if a player types !notes , the Scribe can
output the current objectives or reminders of past events). Internally, it might periodically scan the game
state (including character sheets for level ups or new items) and feed relevant information to the
Storyboard or Writer agent to ensure the narrative accounts for these developments. - NPC/Enemy
Manager: Manages non-player characters (NPCs) and adversaries, including their stats, behaviors, and
initiative order during combat. This agent serves as a database and controller for all NPC-related data. For
instance, if an NPC has a secret motivation or a scripted behavior (from Hidden docs), the NPC agent can
surface that information when the NPC interacts with players. During combat, it tracks turn order and
decides enemies’ actions (which it might pass to the Narrator to describe). It also ensures consistency in
NPC portrayal (e.g. if an NPC lied to the players earlier, it keeps that info so the NPC doesn’t accidentally
reveal the truth later unless intended). - Storyboard Agent: Keeps track of the overall narrative arc and
progress within a campaign. It acts as the long-term memory and planner for the story. The Storyboard
agent might maintain a graph or outline of story nodes: which quests are completed, which plot threads are
unresolved, and what major events have happened. It can remind the Writer or GM agent of these points to
ensure continuity (for example, "the players promised to help the village elder, that thread is still open"). It
can also suggest side quests or bring back old plot elements. This agent is key for longer campaigns to
prevent the AI from forgetting earlier chapters. - Image Generation Agent: Handles creation of visual aids
(scene illustrations, character portraits, item images) via AI image generation services. When invoked with a
prompt and a desired style, it queues a job to generate an image and eventually returns a reference (URL or
file path) for the frontend to display . It supports multiple styles (e.g. "8-bit pixel art", "hand-drawn
sketch", "realistic painting") to match the campaign aesthetic. For performance, it may use lower-resolution
9 10
5
or pre-cached images as placeholders while high-quality generation is in progress. The Image agent also
enforces content safety by using filtered prompts or moderation (to avoid NSFW or disallowed imagery) and
can fall back to a default image if generation fails or is blocked. - Player Management Agent: (Utilityfocused) Handles player-centric operations outside the narrative. This includes account/profile updates,
managing the user’s friend list, and character creation/import logic. It also interfaces with external services
for integration (for example, storing a D&D Beyond API token on a user’s profile for syncing). While not an
"AI" agent, it’s part of the agents module in that it provides services and endpoints for player actions like
accepting invites, creating characters, etc. It ensures that when players perform these actions, the game
state (campaign membership, character records) is updated accordingly and other agents (like the
Storyboard or Scribe) are informed if needed.
Agent I/O Contracts: All agents communicate using structured inputs and outputs, typically as JSON
payloads. For instance, an agent invocation might take a JSON input such as:
{
"campaign_id": "...",
"session_id": "...",
"state_snapshot": { /* condensed game state or relevant context */ },
"player_action": { /* details of the latest player action/input */ },
"document_refs": [ /* IDs or keys to relevant Core/Flavor docs needed */ ]
}
And respond with a JSON output like:
{
"type": "narration" | "roll_request" | "scene_update" | "image" | ...,
"payload": { /* content of the response; structure depends on type */ },
"metadata": { "agent": "Narrator", "confidence": 0.95, "source":
"quest_notes" },
"attachments": [ /* optional, e.g. image IDs or references */ ]
}
This consistent contract makes it easier to debug and test agents in isolation. For example, we can feed a
known state_snapshot to the Scene agent in a unit test and verify it returns a roll_request when
expected. It also allows the orchestrator (GM agent) to treat all agent outputs uniformly and apply generic
policies (like filtering out any outputs marked with low confidence or potentially harmful content).
Orchestration & Fallbacks: The GM/Orchestrator agent is essentially the conductor of the agent ensemble.
In a typical cycle, when it’s time to produce the next bit of game output (e.g. a player submits an action or
it's a new turn), the orchestrator will: 1. Gather the necessary context (game state, relevant documents via
document_refs , recent history, etc.). 2. Invoke the relevant agents. For example, it might call the Writer
agent to outline what happens next, the Scene agent to check for any mechanics (rolls, encounters), and the
NPC agent if any NPCs are involved in the scene. Some agents might run in parallel if their tasks are
independent. 3. Collect the agents’ responses (some may return immediately, others might be
asynchronous tasks that the orchestrator waits for via the queue). 4. Validate and integrate these
6
responses. The GM agent checks for consistency and quality – e.g., if the Writer suggests something that
contradicts known lore or a player’s backstory, the GM could adjust or ask the Writer to regenerate that
part. It also ensures the tone and content adhere to session settings (for instance, keeping it PG-13 if that’s
a setting, avoiding breaking fourth wall, etc.). 5. If an agent’s output triggers another action (like Scene
agent requesting a dice roll), the orchestrator can either handle that immediately (forward to PencilPusher
and wait for result) or send a request back to the client (e.g. prompt the player to roll, though usually we
automate rolling). 6. Once all needed pieces are in place, the GM agent composes the final output event
that will be delivered to players. For example, it might take the Narrator’s descriptive text, insert the result
of a dice roll resolved by PencilPusher, and include an image reference from the Image agent, bundling
these into a coherent update. 7. The orchestrator then emits this final event via the WebSocket to all clients
and logs it (e.g. as a new message in the Message log).
If anything goes wrong during this cycle (an agent fails to respond, or returns an error, or the result is
nonsensical), the orchestrator has fallback strategies. For instance: - If a call to an external LLM times out
or errors, the orchestrator can retry once or twice with exponential backoff, or switch to a simpler built-in
logic (maybe use a smaller offline model or a templated response) to avoid stalling the game. - If an agent
returns content that violates a safety rule (e.g. the Narrator output contains disallowed content or simply
something the GM finds inappropriate), the orchestrator can either censor/modify it or scrap it and ask the
agent again with adjusted parameters. - In worst-case scenarios, the orchestrator can send a generic
message to players indicating a hiccup (“The story pauses momentarily...”) while it recovers, or have prewritten fallback events (like a random ambient event) to keep the game moving.
Queue-Based Workflow: Many agent operations, especially those involving external AI APIs or heavy
computation, will be executed via the background queue. For example, image generation requests and
long-form narrative generation will be job-queued. The orchestrator will initiate those jobs and then either:
- Wait asynchronously for the result (holding the game thread until the result is ready, which is acceptable if
it’s just a few seconds and we inform the user something is happening). - Or, design the game flow to not
block on them: e.g., dispatch an image generation but continue the text narrative, then later when the
image is ready, send another event to reveal the image.
The system uses unique IDs or correlation tokens to tie asynchronous results back to the right context. For
instance, an image generation job might carry the campaign/session ID and some prompt metadata so
when it finishes, the worker knows which session to send the result to and how to integrate it.
Overall, the agent orchestration is designed to be modular and resilient. We can add or remove agents
without disrupting the whole system (for example, if we later create a Voice Agent for text-to-speech
narration, the GM agent could call it after getting the Narrator’s text, and then send audio clips to players).
Likewise, if an agent is causing issues, the GM agent could have a toggle to temporarily bypass it. This
architecture allows TavernTAIls to incrementally improve AI capabilities while maintaining a playable
experience at all times.
7
Features & User Experience
The TavernTAIls platform offers a range of features to facilitate gameplay and ease of use. The focus is on
integrating AI assistance seamlessly into a traditional tabletop RPG workflow, while also providing
necessary social and campaign management features. Key features include:
Campaign Management: Users can create and manage campaigns through a Campaigns
Dashboard. This dashboard lists campaigns the user is involved in (with details like campaign name,
GM or player count, last active date, etc.), and provides options to open or edit a campaign, invite
players, or archive a campaign. Creating a campaign establishes the user as the host (GM) for that
campaign. Campaign settings include the title, description, and possibly game system or privacy
settings. (Eventually, public campaigns or templates might be supported, but MVP assumes private
campaigns you explicitly invite others to.)
Session Lobby & Invites: Within a campaign, the host can start or configure the session. For MVP,
each campaign might have a single ongoing session (the terms can be used interchangeably
initially). Hosts invite players to their campaign via username or email. TavernTAIls includes a Friend
System – users can add each other as friends, which makes inviting easier (you can see your friend
list and invite from there) . Invites can also be sent to any email address (the recipient will get a
sign-up link if they don’t have an account). The host can specify a required character level when
sending an invite (e.g. “need a level 5+ character”). Invitees receive a notification or email and can
accept the invite by selecting one of their existing characters or creating a new character (the system
will guide them to meet the level requirement). Once accepted, the player joins the campaign as a
member. The UI shows pending invites and their status. Only the host (or co-hosts, if that becomes a
feature later) can see and manage all invites.
Character Creation & Import: Players can create characters through a dedicated interface. This
includes choosing a name, class, level, and entering abilities and other stats (or using defaults). To
speed up setup, TavernTAIls will allow importing characters from external sources. In MVP, a basic
approach is supported: for example, the user can paste a JSON export from D&D Beyond or upload a
PDF of a character sheet, and the system will attempt to parse it. The character is then stored in the
user’s personal library and can be reused for different campaigns (if appropriate). The character data
model includes core attributes (like strength, dex, etc.), skills, inventory, and any game-specific stats.
Over time, we’ll enhance this to include leveling logic or integration with external character
management. A user can manage their characters outside of any campaign (view/edit them from
their profile). When accepting a campaign invite, they pick which character to bring, ensuring it
meets any requirements.
In-Session Chat & Turn Tracking: The primary interface for an active session is a chat-like feed
where all narrative output, system messages, and player communications appear chronologically.
This serves as both the storytelling medium (players read the AI’s narrative here) and the action log
(players type their actions or chat). The chat supports markdown formatting for readability (e.g. the
AI can italicize descriptions or bold important names). The interface may separate player messages
from system/AI messages visually (different colors or indents) to distinguish narrative from player
chatter. For asynchronous play, this feed is persistent and can be read back to catch up. A Turn
Queue feature helps coordinate in structured scenarios (like combat or any situation where players
should act one at a time). The UI can display whose turn it is, and maybe highlight that player. In
asynchronous mode, when it’s a particular player’s turn, that player might get a notification (email or
push) and the others see a “waiting for X” status. Players can manually end their turn via a button, or
the GM can override or skip turns if someone is unresponsive.
•
•
11
•
•
8
Dice Rolling Interface: Players and the AI have access to a built-in dice roller. Players can input dice
commands (like /roll 1d20+5 ) or use UI controls (like a dice icon that opens a roller). The results
of dice rolls are injected into the chat log for transparency, showing the formula and result (and
possibly a breakdown of components). The Beyond20 integration allows players to roll from
external character sheets: if a player uses the Beyond20 browser extension linked to our endpoint,
those roll results will appear in the chat as well . The PencilPusher agent ensures consistency and
fairness in rolls. All players see the same result when a roll happens, and rolls are labeled with who/
what initiated them (e.g. “Alice’s roll: [result]”). A roll history might be accessible for reference (this
could be simply scrolling up in chat or a separate log).
Game Master Controls (DM Toolkit): A host (GM) has an elevated set of controls accessible through
a DM sidebar or overlay. These DM Helper tools include:
Viewing and managing Hidden Documents in the UI (e.g. open the campaign’s secret notes, NPC
info, etc., which players cannot see).
Triggering events or overriding the AI: for example, the GM can push a custom narrative text into the
chat (in case they want to manually narrate something or correct the AI), or override a dice roll
(sometimes a GM might fudge a roll behind the screen for a better story).
Adjusting game state: e.g. modify a character’s HP, give experience points, add an item to someone’s
inventory.
Controlling pace: advance to the next scene or pause the session. Possibly a “fast-forward” feature
that forces all agents to wrap up the current scene.
Revealing hidden info: e.g. take a Hidden Document and share it as a flavor text to players at the
right moment (the system could copy its content into the chat or mark it visible).
Teleport or position control: if we have a concept of locations or a map, the GM can move players
around or spawn encounters.
These controls ensure that a human GM (if present) can guide or correct the AI-driven experience and
handle any off-script scenarios. They also allow solo players with GM privileges (someone running a game
for themselves) to influence the narrative if desired. - Notifications & Presence: The platform provides
notifications to facilitate asynchronous play and keep players engaged. Examples: - Invite Notifications:
When you are invited to a campaign, you receive an email notification with a link to accept (and an in-app
alert if you log in). - Turn Notifications: If it becomes your turn in an asynchronous session and you’re not
currently online, the system can send you an email or push notification saying “It’s your turn in Campaign X.”
- Mention/Ping: If a player mentions another (e.g. "@Bob, we need your decision"), the mentioned user
could get a notification if they’re offline. - Daily Summaries: Optionally, a summary of what happened in a
session could be emailed to all players, especially if playing asynchronously (to remind them of the story
state).
Presence indicators show who is currently online in a session (e.g. a green dot by their name) and possibly
who is typing. This helps recreate the feel of a live table where you know who’s present. Users can adjust
their notification preferences in settings to avoid spamming (some may only want in-app notifications vs
emails). - Responsive Design & Accessibility: The UI is built with responsive design principles so that it
works on desktop, tablet, and mobile phone browsers. Layouts will collapse or change appropriately (for
example, on mobile the sidebar panels might turn into swipe-able screens or accordions). Touch controls
are considered (larger buttons for rolling dice, etc., on mobile). We also aim to meet accessibility standards
(like proper ARIA labels, focus management for screen readers) so that a wider range of users can enjoy the
platform. This includes ensuring color choices have sufficient contrast and providing alternatives to any
color-coded info (for colorblind users). Accessibility also benefits the developer workflow (e.g. clearly labeled
components are easier to target in tests). - Future UX Enhancements: Looking beyond MVP, the plan is to
•
12
•
•
•
•
•
•
•
9
incorporate richer media and interactions. This could include: - Visual Map/Board: Displaying a simple grid
or background image for battles, allowing players to move tokens (if we want light tactical support). This
would complement the narrative rather than replace it. - Voice Support: Integrating text-to-speech for the
AI Narrator (so the story can be heard) or speech-to-text for players to speak their actions. This could make
the experience hands-free or more immersive. - Content Library and Marketplace: Allowing users to share
or import community-created content (like a quest module or NPC pack). The AI could then use these as
starting knowledge, making it easier to set up a new campaign. - Multimedia Integration: Inserting
background music or sound effects triggered by story events (requires careful sync with narrative).
These ideas will be considered once the core experience is solid, ensuring TavernTAIls remains lightweight
and user-friendly even as features expand.
External Integrations
TavernTAIls is designed to work with popular RPG tools and content sources, to enrich the gameplay
experience and streamline setup. Key planned integrations include:
Beyond20 (Virtual Tabletop Extension): Beyond20 is a browser extension that sends dice rolls from
platforms like D&D Beyond to virtual tabletops. TavernTAIls will support Beyond20 so players who
have digital character sheets can roll directly from their sheet and have the result show up in our
app. We’ll implement an HTTP endpoint such as POST /integrations/beyond20/roll which
Beyond20 can send roll data to . The payload from Beyond20 will be parsed to identify which
campaign/session and which character the roll is for (the integration might require the user to
specify a campaign token or something in the Beyond20 settings). On receiving a roll result, the
backend will route it through the PencilPusher agent logic (to apply any additional modifiers and log
it) and then broadcast the result to the session chat, labeled appropriately. Note: Beyond20 typically
operates by hitting a local URL (like http://localhost:3000 ) due to how browser security works,
so users might need to run TavernTAIls locally or use a custom redirect page if using our hosted
version. We’ll document the setup for this (it may involve configuring Beyond20’s custom URL
feature).
D&D Beyond (Character Sync): Many players maintain their characters on D&D Beyond. We plan a
two-step integration:
Short-term (MVP/Phase 1): Allow users to manually import from D&D Beyond. This could be done
by copy-pasting the JSON data from D&D Beyond’s character builder (if available) or by uploading a
PDF export of the character. Our Character Import pipeline will parse this information into the
TavernTAIls character model . This is a one-time import (no continuous syncing).
Long-term (Phase 2): Implement an OAuth-based sync with D&D Beyond’s API (if D&D Beyond
provides one, or using their unofficial API with a token). The user would link their D&D Beyond
account by providing a token (stored securely on their TavernTAIls profile). Our server could then
periodically poll D&D Beyond for changes or receive webhooks if supported . For example, every
5 minutes, check if the character’s modified_time changed, and update the TavernTAIls character
record accordingly. This allows near-real-time synchronization of level ups, inventory changes, etc.
We will throttle this to avoid rate limits and give the user control (like a “sync now” button or
adjusting frequency).
A big consideration is compliance with D&D Beyond’s terms of service. We have to ensure we’re accessing
data only for users who have given permission and not scraping protected content. Likely, only character
•
12
•
•
13
•
14
10
data (which the user owns) will be involved, so it should be fine. - PDF Character Sheet Parsing: As part of
the character import, we’ll use libraries like pdfminer.six or PyMuPDF to extract text from PDF
character sheets . The system will apply heuristic rules to identify key fields (e.g. the number after "STR"
is Strength score). We might support a specific template (like the official 5e sheet) initially for best results. If
the text extraction is unreliable (especially if the PDF is scanned or uses fancy fonts), we might incorporate
an OCR step for scanned PDFs or prompt the user to correct any ambiguous fields via a form. This
integration reduces the manual data entry needed when bringing in an existing character, though we’ll
educate users that some tweaking may be needed after import. - AI Image Generation Providers: The
Image agent is abstracted to support multiple providers and choose the most cost-effective or high-quality
option as needed . Potential providers include: - OpenAI’s Image API (DALL·E): Simple to use if already
integrated with OpenAI for text, but might have cost and rate limits. Good for certain styles. - Stability AI
(Stable Diffusion API): They offer a cloud API for Stable Diffusion. We can use this for a variety of styles
depending on the model end-point (some endpoints produce more photorealistic images, others more
artistic). The cost might be on the order of $0.03–$0.05 per image depending on model, which is
manageable if used sparingly. - Replicate: A platform that hosts many machine learning models including
various Stable Diffusion versions and art styles. With Replicate, we can call different models by specifying
the model ID. This gives flexibility (for example, using a pixel-art model vs a watercolor style model).
Replicate charges per second of GPU time; generating one image might cost a few cents. We can integrate
their API by sending the prompt and style parameter. - Local or Self-Hosted Models: For users running
TavernTAIls on their own hardware (or if we later deploy a dedicated server with a GPU), we could integrate
a local stable diffusion instance or other open-source models (like a specialized fantasy art generator). This
avoids per-image cost but requires GPU resources. We might provide an option in settings to use a local
model (pointing to a local server endpoint).
Our architecture will use an adapter pattern for image generation. The user (or GM/agents automatically)
requests an image with a prompt and a style tag. The Image agent then selects a provider (based on
configuration or random if multiple are available for variety), sends the request, and immediately returns an
acknowledgment to the orchestrator. The actual image generation happens asynchronously (since it can
take several seconds). Once done, the image file or URL is saved and a message with the image is sent to
the players. We will implement caching to avoid duplicate costs: if the exact same prompt was generated
before in this campaign, we may reuse the image or at least store it so a refresh doesn’t trigger
regeneration. Content moderation is also crucial; many image APIs have built-in filters. We will catch any
errors or content flags and handle them (maybe by informing the GM that the prompt isn’t allowed, or by
tweaking the prompt automatically to be more acceptable). - Email & Communication Services: The
platform will likely integrate an email service for sending notifications (especially invite and turn emails).
This might be through a service like SendGrid or AWS SES, or simply a local SMTP server for MVP. Though
not an RPG-specific integration, it’s an important part of the tech stack for user communications. - Other
RPG Tools (Future): We have an eye on integrating other tools: - Virtual TableTops (Foundry, Roll20):
Possibly sync data like initiative or allow TavernTAIls to act as a GM on those platforms by outputting
narrative there. This is speculative and would require those platforms’ APIs or extension capabilities. -
Compendiums (Open5e, etc.): An agent could hook into rule compendiums to answer rule questions. E.g.,
if a player asks “what does the spell Fireball do?” an agent could fetch that info from an open 5e SRD API or
database. - Voice Platforms (Discord, etc.): Integration to allow playing via Discord (e.g. a Discord bot that
mirrors the TavernTAIls session into a Discord channel) could be interesting to reach more users. This would
be a later, separate connector.
9
10
11
Each integration is implemented with modularity and user control in mind (users can choose whether to
use them). They will also be gated by API keys or credentials stored in configuration, so the platform can
run without them if, say, no keys are provided (ensuring that lack of an integration doesn’t break core
functionality).
Data Model & API Structure
To support the above features, TavernTAIls defines a set of core data entities and corresponding API
endpoints. The design follows RESTful conventions, using JSON for data exchange (except for binary file
uploads). Below is an overview of key models and their APIs:
Core Data Entities (Database Tables):
- User: Represents a user account. Fields include unique username or email, password hash, and profile
info (display name, etc.). Also stores preferences (like notification settings, and possibly an OAuth token for
integrations if provided). - Friend: Represents a friendship or pending friend request between users. Could
be a join table of user-to-user with status (pending/accepted). - Campaign: Represents a campaign. Fields
for name, description, host (user id of GM), creation date, status (active or archived). May also track game
system or settings related to the campaign. - Session: Represents a game session instance. Initially, it might
be 1:1 with Campaign (one active session per campaign), but we have a separate table to allow multiple
sessions (like chapters or separate adventures) within a campaign down the line. Fields: campaign id, start
time, maybe end time or last active timestamp. - Invite: Represents an invitation for a user to join a
campaign. Fields: campaign id, inviter user id, invitee (could be user id if the user exists or an email if not
yet registered), required_level, status (pending, accepted, declined). If accepted, we might link the chosen
character. - Character: Represents a player character. Fields: owner user id, campaign id (if the character is
currently in a campaign; could be null if not currently assigned), name, level, class, race, stats (possibly as
JSON blob for flexibility: attributes, skills, spells, inventory, etc.), and metadata like creation date. If a
character is imported from an external source, we might store an external ID or source reference. -
Document: Represents a document or file stored in a campaign. Fields: campaign id, uploader user id,
name, type (Core/Flavor/Hidden), storage path or URL, maybe size and filetype, and a version or revision
history link. If using embeddings, might also have an embedding vector or reference to one. - Message:
Represents a chat or narrative message in a session. Fields: session id (or campaign id), sender (could be a
user id for player messages or a special ID for system/AI messages), timestamp, content (text, or could
reference an image or other attachment), and a message type (e.g. "player", "narration", "roll_result",
"system"). This is used to persist the session log. - Roll: (Optional separate table) Represents dice rolls. We
could log rolls in the Message table with a type, but a separate Roll table can store numeric results, dice
formula, and which message it corresponds to. This could be useful for analytics or if we want to present
stats (like average damage) later. - AgentEvent: Represents an event or action by an AI agent (narrative
generation, scene analysis outcome, etc.). This is mostly for debugging/audit – storing raw inputs/outputs
of agents. Not critical for gameplay but useful in development; might be toggled via a debug mode due to
volume.
Selected API Endpoints: (grouped by feature area) - Auth & User:
- POST /player/signup – Register a new user account. In development, email verification might be
skipped or done via a returned token. In production, this could trigger a verification email. - POST /
player/login – Log in with credentials, returns JWT (and refresh token if implemented). - GET /player/
me – Get current user’s info and profile settings (requires auth token). - POST /player/friends – Send a
friend request to another user (or accept one). The exact API might differentiate actions via payload or
12
separate endpoints ( /friends/{id}/accept etc.). - GET /player/friends – List friends and pending
requests for current user. - (If refresh tokens are used: POST /player/token/refresh – to get a new
access token.) - Campaigns:
- POST /campaigns – Create a new campaign (current user becomes host/GM). - GET /campaigns –
List campaigns the current user is part of (as host or player). Possibly include invitations here or we have a
separate invites endpoint. - GET /campaigns/{id} – Get details of a specific campaign (if the user is a
member or has the invite). - PUT /campaigns/{id} – Edit campaign (only host can, e.g. update
description or archive it). - POST /campaigns/{id}/archive (or via PUT with a status field) – Archive or
deactivate a campaign. - Sessions & Membership:
- POST /campaigns/{id}/sessions – Create a new session in a campaign. This might set up a new
session record. For MVP it might not be needed (one session auto-created). - GET /campaigns/{id}/
sessions – List sessions in a campaign (for future use if multiple). - POST /campaigns/{id}/invite –
Invite a user to campaign. Payload could include email or username and min_character_level .
This creates an Invite and sends notification. - POST /campaigns/{id}/join – Accept an invite (the user
hitting the invite link could trigger this, with their chosen character info in payload). - DELETE /
campaigns/{id}/members/{userId} – Remove a member (in case of kicking someone or someone
leaving). - GET /campaigns/{id}/members – (if needed) list members and their roles (player or co-GM). -
GET /sessions/{id} – Get session state or metadata (if we expose anything, e.g. active turn, etc.). -
WS /campaigns/{id}/ws – WebSocket endpoint for live updates in that campaign’s session . -
Characters:
- POST /characters – Create a new character. If sending raw data (like via a form) or possibly include a
file for import. Alternatively, we might have sub-endpoints: POST /characters/import etc. - GET /
characters – List the current user’s characters (with option to filter by those not in campaigns). - GET /
characters/{id} – Get character details (only allowed if current user owns it, or if it’s shared in a
campaign where current user is GM). - PUT /characters/{id} – Update a character’s information. For
example, after a level-up or to correct an import. - Possibly DELETE /characters/{id} – Remove a
character (if not currently in a campaign). - Documents (File storage):
- POST /campaigns/{id}/documents – Upload a document to the campaign. This would be a multipart
form if it's a file upload. Fields for type (core/flavor/hidden) and maybe an optional description or tags.
The file binary goes in the form data. - GET /campaigns/{id}/documents – List documents in the
campaign (the response will be filtered by the user’s permissions, e.g. a player will not see hidden docs
here). Could support query param to filter by type. - GET /documents/{id} – Download a specific
document file (if the user has access). Might stream the file. - Possibly DELETE /documents/{id} –
Remove a document (only host or owner if we allow). - Messages & Chat:
- GET /campaigns/{id}/messages – Get recent messages in the session (with pagination or since a
certain time, for lazy loading chat history). - POST /campaigns/{id}/messages – Post a new message to
the session. For players, this is their chat message or action. For the client, this could also be used to send
game commands (like an action the AI should process). The backend will determine if it’s a player message
or a command (some convention like messages starting with "/" might be treated as commands). - The
WebSocket will also deliver new messages in real-time so the client often doesn’t need to poll this GET after
initial load. - Dice & Rolls:
- POST /campaigns/{id}/rolls – Request a dice roll (e.g. from the UI). The payload might include a
formula and possibly context of which character or skill. The server responds with the result (and
broadcasts it via WS). - POST /integrations/beyond20/roll – Endpoint for external dice results (from
Beyond20) . It will verify the payload, map it to a campaign and character, then produce a roll result
event in the session. (This might internally call the same logic as above to unify handling.) - GET /
6
15
13
campaigns/{id}/rolls – Retrieve roll history (if not using messages for that). - Agent & AI Endpoints:
(Mostly internal or admin-facing; these might not all be exposed to end-users) - We may have endpoints like
POST /agents/narrator or POST /agents/gm for debugging or development, where we can send a
test payload to an agent and get output (useful for developing prompts or testing AI without full session
context). In production, these wouldn’t be used by front-end; the orchestrator calls agents via function or
internal API. - POST /images/generate – Request the Image agent to generate an image from a
prompt. (If we treat it as part of documents or messages, we might instead have
POST /campaigns/{id}/images which essentially does similar.) This will likely immediately return a job
ID or placeholder, and the actual image URL will come via WebSocket event when ready.
API Design Notes: - All protected endpoints require the Authorization header with a Bearer token (JWT). We
will implement middleware to check this and attach the user to the request context. - We use standard HTTP
responses and codes (201 for created, 400 for validation error, 403 for forbidden, etc.). Errors will return a
JSON with an error message and possibly a code. - For file uploads and downloads, appropriate ContentType and Content-Disposition headers are set so that browsers handle them correctly (inline for images
maybe, attachment for other files). - The WebSocket protocol might have its own message structure, e.g.
JSON messages with a type field (such as "message", "roll_result", "turn_update", "image") so the client
knows how to handle incoming events. - If needed, some GET endpoints (like listing campaigns or
messages) can be enhanced with query parameters for filtering, searching, or pagination (e.g. ?
before=<id> to get earlier messages). - The API will be documented (likely via an auto-generated
OpenAPI spec from FastAPI, which can produce docs) so that developers or even advanced users can
integrate with it.
By structuring the API around these resources, we ensure clarity and RESTfulness, making it easier to
maintain and extend. Each new feature likely corresponds to a new resource or an extension of an existing
one (e.g. adding a PUT /sessions/{id}/turn when implementing turn skipping by GM, etc.). The
database schema will evolve with features (we’ll use migrations to keep it in sync).
Persistence & Storage Details
Database: The development environment will use SQLite (file-based database) for simplicity, but
production will migrate to PostgreSQL for robustness and concurrency support . We will manage
schema changes with Alembic (for SQLModel) so that we can version control the DB structure. Key
points:
Use foreign keys with cascade rules where appropriate (e.g. if a campaign is deleted, maybe autodelete invites and sessions, but likely we’ll prefer soft-deletion or archiving rather than hard deletion
for most things, to preserve history).
Ensure indexes on key lookup fields (like looking up messages by session, invites by campaign+user).
Utilize JSON columns for flexible data (e.g. character stats, which can vary by game system, might be
stored in a JSONB field in Postgres).
The pgvector extension can be installed in Postgres to store embedding vectors for documents
. If we use this, we’ll have an index on those vectors to allow similarity search.
Regular maintenance: In production, we should plan for periodic backups of the database. Given
likely small size (text data mostly), dumps can be done nightly and stored securely.
File Storage: During development, we store files (session documents, generated images) locally
under a data/ directory structured by campaign. For production, we abstract this so it can be an
•
4
•
•
•
•
4
•
•
14
S3 bucket or similar. The system will treat file paths as opaque keys beyond the storage service. For
example, we might implement a Python class StorageService with methods
save_file(campaign_id, file) and get_file_url(doc_id) that either writes to disk or to
cloud and returns a URL. If using S3, we may use presigned URLs or a proxy route for downloads.
Permissions: Hidden documents will either not be accessible via direct URL (if they are, the URLs
should be secret/unguessable and possibly short-lived if presigned).
We will enforce size limits for uploads (configurable, e.g. no more than 10 MB per file for now) to
avoid abuse or performance issues.
If needed, we’ll implement virus scanning for uploads (especially if allowing PDFs from users, to
avoid storing malicious files) – likely using a library or an external service.
For images generated by the AI, since those are created by our service, virus scanning is not an
issue, but we still store them similarly. We might also downscale images to a maximum resolution to
save space if the generation gives a very high-res image.
When moving to cloud storage, we might place images in a public bucket (with names that don’t
reveal anything sensitive) for direct access, whereas documents might be in a private bucket
requiring presigned URLs for download to enforce auth.
Caching & Session State: We will run a Redis instance (or an alternative like Python’s
functools.lru_cache for trivial caching) for:
Caching frequently used data: e.g. game rules data or results of heavy computations if needed.
Pub/Sub for WebSockets: As discussed, Redis can channel messages between processes for
realtime events.
Task queue broker: Celery or RQ will use Redis to queue jobs and track their status. The advantage
is Redis is lightweight and serves multiple purposes here.
Rate Limiting counters: We can use Redis to store counters for API calls per IP or user to enforce
limits (like X requests per minute for certain endpoints) .
Session ephemeral data: If we need quick ephemeral storage (like a mapping of user ID to current
WS connection or turn timers), we can also use Redis for that.
Scalability & Performance:
Even for MVP, we should consider N+1 query issues and heavy loops. Using the ORM effectively (with
joins or preloading relationships) or writing raw SQL for critical queries can prevent slowdowns.
As the dataset grows (imagine long campaigns with thousands of messages and many docs), we
may introduce pagination and archive older data. For example, archiving old chat messages (or
summarizing them via the Scribe agent) to keep the active log shorter.
We might also consider search indexes for messages if needed (like if we want to allow players to
search chat logs, we could use Postgres full-text search on the Message table).
Content delivery: For static assets (images, PDFs), serving them through a CDN or from S3 directly
will offload that work from our app server. In MVP it’s fine to have the FastAPI serve files, but in
production we’d likely front with Nginx or rely on S3’s delivery.
Collaboration & Offline: There is an open question about moving session data (like documents/
notes) to the DB for real-time collaboration . If we anticipate multiple users editing a note
simultaneously, a DB-centric or specialized collaboration service (like Yjs or operational transforms)
might be needed. For now, we keep it simple: one user editing at a time (others get read-only until
saved, perhaps).
Offline caching for mobile: We haven’t planned a PWA (Progressive Web App) with offline support
yet. Possibly in the future, we could cache recent chat logs or allow read-only access to docs when
offline. But active gameplay likely requires server connection (for AI and others), so we consider
offline out-of-scope for MVP except maybe caching static docs.
•
•
•
•
•
•
•
•
•
16
•
•
•
•
•
•
•
17
•
15
In summary, our persistence stack (Postgres + optional Redis + optional S3) covers the needs for a scalable
application, and we’ve made sure it’s flexible enough to switch out pieces (like using a different vector DB,
or using local disk vs cloud storage) with minimal code changes due to abstraction layers.
Security & Authentication
Security is critical for TavernTAIls, both for protecting user data and for ensuring game integrity (preventing
cheating or leaks of hidden info). Key security measures include:
Authentication (AuthN): We use JWT (JSON Web Tokens) for stateless authentication of API
requests . On successful login ( POST /player/login ), the server issues an access token (JWT)
signed with our secret key. This token encodes the user’s identity and expiration time. The client
stores this (likely in memory or secure storage) and includes it in the Authorization header for
subsequent requests. We will likely implement refresh tokens for a smoother user experience (so the
user stays logged in beyond the short life of access tokens). The refresh token could be stored as an
HttpOnly cookie or returned and stored similarly securely. The server will have an endpoint to
refresh ( /player/token/refresh ) which checks the refresh token and issues a new access token
if valid. Refresh tokens can be long-lived but are revocable (we might keep a whitelist/blacklist of
tokens in the DB for logout/revocation).
Authorization (AuthZ): Role-based and permission-based checks are enforced on every relevant
endpoint:
Only the host (GM) of a campaign can send invites, remove players, upload hidden documents, or
access hidden content.
Players can only access campaigns they are members of. Trying to access another campaign’s
endpoints yields 404 or 403.
Only a user themselves can view or edit their profile/characters (except that a GM can see a player’s
character sheet within their campaign, which we consider allowed game behavior).
Admin-level actions (if any, like deleting content or viewing all games) are reserved for admin users
(we might have an is_admin flag on User).
The system will double-check critical operations: e.g., when posting a message or roll, verify the user
is indeed in that session.
Hidden document access: the endpoint serving document files will check the user’s role before
returning a file marked as Hidden (to ensure players can’t fetch it even if they guess an ID).
Data Validation & Sanitization: All input from clients is validated using Pydantic models or explicit
checks. This prevents malicious data from causing issues. For example:
Strings that will be used in SQL queries (if any raw queries exist) will be parameterized properly to
avoid SQL injection.
File uploads will have their filenames sanitized (we might ignore the client-provided name and
generate our own to avoid path traversal or special char issues).
The content in chat messages is plain text except maybe simple markdown—we will sanitize or
escape any HTML or scripts to prevent XSS. Since our app is controlling the rendering, we ensure
that e.g. a player’s message that says <script> doesn’t get executed in anyone’s browser. Using a
library or restricting formatting to a safe subset will help.
The AI outputs should also be sanitized before sending to clients (though mostly they are textual
narrative, but we wouldn't want them to accidentally produce a string that triggers some unwanted
behavior in the UI).
•
16
•
•
•
•
•
•
•
•
•
•
•
•
16
Rate Limiting & Abuse Prevention: We will enforce rate limits on API endpoints to mitigate bruteforce and spam:
Login attempts: limit by IP and account to prevent password brute force (e.g. no more than 5 failed
logins per minute per IP).
Message sending: prevent a single user from spamming dozens of messages per second (both for
abuse and performance). We can allow a generous rate for normal use, but cut off extremes.
Agent triggers: especially endpoints or actions that cause expensive operations (like image
generation or long AI calls) will be limited per user (and maybe globally) to control cost and load .
For example, maybe 5 image generations per hour per user.
Invitation sending: limit how many invites one can send in a short period to avoid someone using it
to spam emails.
These limits can be implemented via a simple in-memory counter or using Redis as mentioned, and
returning HTTP 429 Too Many Requests when exceeded.
Secure Communication: All client-server communication will be over HTTPS in production. This
includes WebSockets (wss). We will obtain SSL certificates (e.g. via Let’s Encrypt) for any deployed
domain, or advise self-hosters to do so. This prevents eavesdropping on token or data in transit.
Password Storage: User passwords are hashed using a strong algorithm (e.g. bcrypt or Argon2) and
never stored in plaintext. On signup, we also enforce basic password strength (minimum length,
etc.). Optionally, allow OAuth (Google, etc.) login in the future to avoid storing passwords at all, but
not in MVP.
Session Management: Because we use JWTs, we are stateless by default. We will, however, have a
way to revoke tokens (for example, if a user changes password or we suspect theft). This could be
done by tracking a token version in the DB or an allowlist of valid refresh tokens. Logging out will
involve removing the refresh token on server side (so it can’t be used).
Content Security (AI outputs): We will apply filters to AI-generated content to avoid disallowed
material (this is both a safety and a user comfort issue). For text, we can use OpenAI’s moderation
API on the outputs or have our own list of banned words to flag. The GM agent will ideally handle
this by instructing the AI to stay within certain boundaries and checking outputs. For images, as
mentioned, we rely on provider filters and some prompt sanitization. If the AI were to ever produce
something sensitive (like exposing a hidden plot detail incorrectly), the orchestrator or DM should
catch it. This overlaps with game integrity but is worth noting as a security of narrative info.
Privacy & Data Protection: We will have a basic privacy policy for users. From a technical side:
We don’t share user data with third parties except what’s necessary for the integrations they enable
(e.g. if they link D&D Beyond, we fetch their data from there at their request).
Personal info stored is minimal (we don’t store full names or addresses, mainly email and maybe a
display name).
We will comply with user data deletion requests (if a user deletes their account, we remove or
anonymize their data).
The content created in campaigns (stories, characters) is user data; we treat it as private within that
group. If we ever use it to train models or similar, it would be opt-in.
Administrative Security: If an admin interface or admin account exists, ensure that it has extra
protection (e.g. 2FA or IP restrictions if needed). At MVP we might not have a separate admin UI, but
we might protect certain actions (like wiping a DB or managing content) behind an admin flag.
Game Integrity (Anti-Cheating): We acknowledge that in a coop RPG, cheating is not a major
concern like in competitive games, but still:
Players cannot alter dice outcomes – those are generated server-side.
If players tamper with their local data (like editing a character in dev tools mid-game), the
authoritative state is on server, so it won’t persist or be accepted unless they have permission.
•
•
•
•
16
•
•
•
•
•
•
•
•
•
•
•
•
•
•
•
17
The GM can fudge things, but that’s an allowed aspect (the GM role is to have final say).
If a malicious player somehow got access to hidden docs (say through an exploit), that would ruin
the experience, so we focus on closing any such holes.
Auditing: We keep logs for important actions. For instance, whenever a Hidden document is
accessed or revealed, log which user (host) did it . Similarly, if any admin actions are taken or if an
unusual event occurs (like a rule override), log it. These logs can help in investigating any issues (like
“how did this secret leak?”).
Deployment Security: Ensure that in deployment, secrets (JWT secret key, AI API keys, email
credentials) are properly stored (environment variables or a secure vault) and not exposed in code
repositories. The Docker images should not contain secrets either. We will provide a sample .env
file and instruct on securing it.
Third-Party Library Security: We’ll keep dependencies updated to pull in security fixes. Use trusted
libraries (FastAPI, etc. are well-regarded). Possibly run a scanner (like Dependabot or pip-audit )
periodically.
In essence, security is woven into each feature: for every endpoint, we ask “who can access this and what
could go wrong?” and test accordingly. By following best practices (like the principle of least privilege and
defense in depth), we aim to make TavernTAIls a safe platform for its users and their creative content.
Developer Experience & Workflow
From the outset, TavernTAIls is being built to be developer-friendly, with an emphasis on automation and
using AI assistance in the development process. This section outlines the tools, workflows, and
recommendations for developers (including those using AI coding assistants like GitHub Copilot or GPTbased tools) to effectively work on the project.
One-Command Setup: To streamline local development, we provide a PowerShell script startapp.ps1 (and a corresponding shell script for Mac/Linux if needed) that automates the
environment startup . Running this script from the project root will:
Terminate any leftover processes that might conflict (commonly, kill any existing Uvicorn or React
dev server instances to free the ports).
Start the FastAPI backend (for example, by running Uvicorn on localhost:8000 with auto-reload).
Start the React development server ( npm start on port 3000).
Optionally, tail logs to a console or output logs to a file for easy monitoring of both backend and
frontend outputs.
This ensures that a developer can get the entire app running with a single command, without manually
starting multiple processes. The script also helps avoid common pitfalls, like port collisions or forgetting to
activate the Python virtual environment. For developers on different OSes, if PowerShell is not available, we
document the equivalent manual steps or provide a simple Python script or Makefile target to do the same.
Consistency of dev environment is key; we might use a .env file for both backend and frontend (frontend
can read env vars at build time for API URL, etc.). - Pre-configured Dev Data: The dev environment is set up
with some default data to facilitate testing. For example, on first run, the backend seeds a default user (e.g.
test@example.com with password secret ) and maybe an example campaign, so you can log in
immediately and see something. It might also create example characters or documents for quick UI checks.
This is indicated in the Completed Milestones (auto-seeded dev user) . We will ensure these seeds run
only in a development mode (to avoid creating dummy data in production). They provide a convenient
•
•
•
16
•
•
•
5
•
•
•
•
18
18
starting point and also serve as examples for writing tests and new features. - Modular Code Structure: We
maintain a clear project structure dividing concerns, which not only aids human developers but also AI
assistants in locating and working on relevant sections: - Backend is organized under server/ with
subpackages for auth , agents , models (for DB schemas), routes (could be split by feature if not in
agents), etc. Each agent might have its own module as described, and each feature (like campaigns,
characters) has its own router and schema definitions. - Frontend is under client/src/ with logical
grouping, e.g. components/ for UI components, pages/ for page-level components, services/ or
api/ for API calls, and perhaps agents/ for any agent-specific UI logic (like a component that renders
the AI’s output in a fancy way or collects multi-step input for an agent). - Shared utilities are in obvious
places (e.g. utils/ for helper functions, constants in a config). - Consistent naming conventions and file
organization means that when using AI code generation, we can easily instruct it where to add code (e.g.
"Add a new endpoint in server/routes/campaign.py for archiving a campaign") and it won’t struggle
to find the right place. - AI-Assisted Development: We heavily leverage AI coding assistants in our
workflow. The detailed work packages (see below) are written almost like prompts for an AI developer –
each has scope, deliverables, and acceptance criteria, which we can feed into a GPT model to generate code
or tests. - Prompting style: When using an AI to generate code, we include context in the prompt such as
relevant parts of this design document (for consistency), the function signatures or schemas it should
interact with, etc. We break tasks down: e.g. first ask it to produce the data model and migration for a new
entity, then separately generate the API endpoints, then the tests. This iterative approach plays to the AI's
strength in handling focused tasks. - We also use AI for boilerplate: writing repetitive CRUD endpoints or
basic forms in the UI can be done quickly by AI given one example. For instance, after writing one similar
router, we can prompt the AI to create another following the pattern. - Codex/GPT-5.1 mini integration: If
available, we might integrate a smaller local model for autocompletion or simple tasks to reduce
dependence on external APIs. For example, a GPT-5.1 mini could be used in an IDE for suggestions or for
running local test scenario generations (like generating fake data). - Quality control: AI suggestions are
reviewed by human developers. We treat AI as a junior pair programmer—great for speed, but everything it
writes is reviewed and tested. We especially scrutinize security-related code written by AI and any logic for
correctness. - We maintain thorough comments and docstrings in code. Not only does this help human
understanding, it gives better context to AI if we later ask it to modify something. For instance, a docstring
on the GM orchestrator function describing its steps will guide an AI if we ask it to extend that function’s
logic. - Automated code generation: We might script certain generation tasks. For example, if adding a
new agent, we could have a template and use a script (or even an AI-assisted script) to generate the
skeleton files for its backend and frontend parts. This ensures consistency and saves time. - Source Control
& CI Integration: We use Git (with GitHub) for version control. Branches for features, pull requests for
merging. GitHub Actions is set up to run tests and linters on pull requests, so we catch issues early . We
also consider using commit hooks (via pre-commit config) to auto-format code (Black, Prettier) and run
basic lint checks before commits, making code style consistent. - Code reviews are required for merging PRs
(at least one approval). AI can assist in code review too: we can use it to analyze a diff and point out
potential issues, but final judgment is by a human. - We might maintain a CHANGELOG and use
conventional commits to help auto-generate release notes. This ties into developer experience by making it
clear what changed when. - Testing & CI: (Detailed in the next section) We emphasize writing tests
alongside features. AI can be used to draft test cases as well. For instance, once we implement a new
endpoint, we can prompt the AI to create some pytest functions to test it (feeding it the acceptance criteria
as basis). This helps ensure we cover expected behaviors. Our CI will run these tests in a matrix (multiple
Python/Node versions to catch compatibility issues). - We also consider automated testing of the front-end
with AI: e.g., using Playwright to script a scenario, or even using an AI to generate those scripts by
describing the scenario in English. This could expedite writing end-to-end tests. - Logging and Monitoring:
19
19
During development, having good logging is a huge time-saver for debugging. We set the logging level to
DEBUG in dev, and log details such as: when an agent is invoked and returns, what key decisions the
orchestrator made (e.g. “Roll needed: sending roll_request to client”), and any errors with stack traces.
These logs are viewable in the console or log files. - For an AI-heavy application, logging the inputs and
outputs (maybe truncated or abstracted for brevity) of AI calls is important. It allows us to debug why an AI
might be giving a weird response by seeing what prompt it got. - We also possibly integrate a tool like
Sentry for capturing exceptions in development and (later) production. That way, unhandled exceptions or
errors get reported, and we can fix them proactively. - Developer Collaboration: We keep documentation
(like this plan, a README, and possibly design docs for tricky parts) up to date in the repo. If multiple
developers (and AI is almost like a developer here) are working, these docs and an issue tracker (GitHub
Issues for each work package) keep everyone aligned. We’ll likely create GitHub issues for each work
package, copying the acceptance criteria into the issue description (as suggested in the breakdown file) .
This way, progress can be tracked, and one can even imagine hooking an AI to respond or provide initial
PRs for those issues. - Continuous Deployment Option: While not required at the start, we plan for an easy
deployment process. Possibly a Docker container that can be run on a server or cloud service. Developer
experience extends to deployment: a contributor should be able to spin up the entire stack (maybe via
docker-compose up ) to test in a production-like environment. We’ll include a Dockerfile and
compose file to that end. If we integrate CI with deployment (CD), any push to main (or a specific tag) could
auto-build and deploy to a test server. This ensures that when developers merge code, it’s quickly verifiable
in an environment that mirrors production (which helps catch environment-specific issues). - Using AI for
Maintenance: Beyond coding new features, AI can assist in maintenance tasks: - Upgrading dependencies:
ask AI to update package versions and fix any breaking changes. - Refactoring: feed it a code section and
ask for suggestions to improve readability or performance. - Documentation: AI can help generate user
documentation or in-app help based on our design docs (for instance, generating a tutorial text or tooltips).
- Even generate assets: maybe using DALL-E or similar to create some default avatar images or background
art for the app (ensuring usage rights are fine).
By integrating these developer experience considerations, we aim to make development efficient and
enjoyable. The use of AI in the workflow not only accelerates progress but also aligns with the spirit of the
project (AI-assisted gaming, AI-assisted development!). New contributors should find a well-organized
codebase, clear tasks, and plenty of automation to help them get up to speed and contribute meaningfully.
Testing, CI, and Quality Assurance
Quality assurance is crucial, especially with AI components that can introduce unpredictability. Our testing
strategy covers unit tests for individual components, integration tests for multi-component interactions,
and end-to-end tests for user flows. Continuous Integration (CI) is set up to run these tests and checks on
every push, ensuring we catch issues early.
Unit Testing: We use pytest for Python unit tests and Jest (with React Testing Library) for frontend
unit tests . Every significant function or module has corresponding tests:
Backend unit tests will cover: utility functions (e.g. dice roll parser), data model methods (if any logic
in them), and each agent’s core logic (for stub agents or any deterministic behavior we implement).
For instance, test that the PencilPusher correctly calculates outcomes for a variety of dice strings, or
that the Scene agent’s trigger detection works for certain input strings.
We can use fixture data for tests, and pytest fixtures to set up common scenarios (like a fixture to
create a user and auth token, or to populate a sample campaign with a character and a doc).
20
•
19
•
•
20
For the AI parts, since the actual LLM calls are non-deterministic and possibly external, we will mock
those. E.g., we can monkeypatch the OpenAI API call to return a predefined response (for test
purposes) so that tests don’t rely on external services and are deterministic.
Frontend unit tests will cover: React components (rendering correct output given props, handling
user interactions calling appropriate functions), and any pure functions (like a helper that formats
text). We’ll simulate events like clicking a roll button and ensure it calls the API with proper data
(mocking the API module).
Integration Testing: These tests ensure that different parts of the system work together as
intended, without necessarily involving a browser. For the backend, we can use FastAPI’s TestClient
to spin up the API and simulate sequences of requests as a test user.
Example: an integration test for the invite flow might: create two users, create a campaign with one,
have that user send an invite to the other, simulate the other accepting (which requires picking or
creating a character), and then verify that the campaign membership updated and that appropriate
notifications (maybe a record or email send call) happened.
We’ll use an in-memory SQLite or a transaction rollback approach to isolate tests (FastAPI’s testing
docs show how to override dependency to use a test database).
Integration tests can also simulate an entire "round" of gameplay in a simplified way: e.g., a test
could call the relevant orchestrator function directly with a dummy state and dummy agent outputs
to see that it produces the expected composite output (without needing actual WS or client).
We might create some fake implementations of agents (for test mode) that instead of calling real AI,
just return predictable outputs. That way we can test the orchestrator logic deterministically. For
example, a DummyNarrator agent could always return "Test narrative." and in tests we set the
orchestrator to use DummyNarrator.
Database migration integrity can be tested by running the migrations in a fresh test DB and verifying
the tables exist, etc., but Alembic is usually reliable.
End-to-End (E2E) Testing: Using a tool like Playwright or Cypress, we will automate browser
interactions to test full user scenarios from the UI perspective . These tests run a headless
browser, so they involve the actual frontend and backend running (often in a test mode).
We might set up a special testing build or use Node to run the React app and FastAPI app in test
mode for these.
Example E2E: Start the dev server, run a test that goes through signing up a new user, logging in,
creating a campaign, inviting a friend (maybe use a second browser context as the friend), accepting
the invite, and then sending a few messages and ensuring they appear for both users.
Another E2E test: the solo play scenario – user creates campaign, performs an action, and the AI
stub responds with a narrative. Validate that the narrative appears in the chat.
Playwright can also help simulate things like network delays or offline status, which we could use to
test the turn notification (e.g., mark one user offline and see that an email was "sent" when it's their
turn).
We will be careful to make E2E tests not flaky: use waits for elements to appear, etc., and maybe stub
out calls to external services (like if the app tries to actually call OpenAI during the test, ensure it’s
hitting a mock server).
Because E2E tests can be slower, we might not run the full suite on every commit, but at least on
main branch merges or nightly. A small smoke E2E (like login→basic gameplay) can run on each PR
to catch fundamental issues.
Test Environment & Data:
•
•
•
•
•
•
•
•
•
21
•
•
•
•
•
•
•
21
For automated tests, we will use configurations to isolate from dev or prod data. Typically, we use a
separate database (or a transient one). We can run tests in parallel if possible (pytest can, but need
to ensure no test interferes with another — using transactions or separate DBs).
We might include some sample files (like a sample PDF, sample D&D Beyond JSON) in a tests/
assets directory to use in import tests.
Fake API keys for testing (or we disable calls). E.g. set environment variable to indicate "use fake
image generation" so that when tests run, the image agent just returns a placeholder immediately.
We ensure tests clean up after themselves, or use fixtures that tear down (like remove any files
written to data/test/ directory).
For front-end tests, we might stub network calls by using MSW (Mock Service Worker) to simulate
API responses if not using a live backend. Or in E2E, use a real backend but running in test mode.
Continuous Integration (CI): We set up GitHub Actions to run our test suites and linters on every
push/PR . The CI pipeline will likely include:
Install dependencies (cache them for speed).
Run backend unit/integration tests (perhaps in one job matrix with different Python versions as
specified).
Run frontend unit tests (with possibly different Node versions matrix).
Run an E2E test job (this one might build the frontend and backend Docker images, start them, then
run Playwright tests).
Run linters: for Python (flake8, maybe mypy for type checking), for JS/TS (eslint).
Possibly run security analyzers (there are GitHub Actions for checking common vulns or secrets in
code).
We expect contributors to ensure tests pass locally, but CI is the gatekeeper.
If a test fails in CI, we fix it promptly; tests are part of the definition of done for each work package.
Code Coverage: We will measure test coverage (using pytest-cov and Jest’s coverage) to see how
much of the code is covered by tests. While 100% is unrealistic (especially because we won’t "test" AI
content quality easily), we aim for a high percentage on the deterministic parts. If coverage falls or
certain modules are untested, we address that. Possibly enforce a coverage threshold in CI (though
we might start with just reporting it).
Manual Testing & QA: In addition to automated tests, the team (or a QA person if available) will do
manual exploratory testing, especially of the game experience. Since AI can behave unexpectedly,
we’ll do test playthroughs:
Simulate a full solo session with a variety of actions to see if any crashes or logical errors occur.
Test on multiple devices/browsers for UI (Chrome, Firefox, mobile Safari, etc. to ensure
compatibility).
Ask some external folks (alpha testers) to try the MVP and give feedback on any issues.
Testing AI components: One challenge is verifying that AI-driven features work as intended. We
can’t unit test creativity, but we can test the integration:
As said, use stub outputs for tests to cover logic around them.
For some baseline sanity, we might have a "regression test" for the AI prompt format: e.g. if we have
a prompt template for the Narrator agent, we can test that it contains certain keywords or not
beyond a threshold. If someone changes the prompt template inadvertently, a test could catch that
by checking a checksum or expected content in the template.
Perhaps maintain a few canned scenarios and expected AI responses in a golden file (though AI
nondeterminism means this can only be approximate). Alternatively, use a very deterministic small
language model locally to simulate the AI for test (not reflecting real quality but at least consistent).
•
•
•
•
•
•
19
•
•
•
•
•
•
•
•
•
•
•
•
•
•
•
•
•
22
Performance Testing: Not immediately in CI, but eventually we might simulate many users or long
sessions to see how the system holds up (e.g. load test the WebSocket, large file uploads). This could
be done with tools like Locust or JMeter. For now, ensure our design (background jobs, etc.) handles
at least a moderate load.
CI for Workflow Automation: We can extend CI to help our workflow:
Linting and formatting can be auto-fixed or commented on PRs (to nudge contributors).
After tests pass on main, we could deploy to a staging environment automatically (if we set up one).
We might use GitHub Actions for cron jobs like running a daily E2E test or checking dependency
updates, then alerting us if something breaks.
Acceptance Criteria as Tests: We closely align tests with the acceptance criteria listed for each
feature. Ideally, every acceptance bullet corresponds to at least one test. This ensures we truly meet
the specified requirements. It also means if someone accidentally breaks a feature later, a test failing
will quickly pinpoint it.
Continuous Deployment (CD): Once confidence in stability is high, we might adopt CD to a
production server. Likely, though, we will manually deploy MVP to control timing. But we will have
Docker images built in CI, which could be pulled to a server and run. We should test the deployment
process a couple of times before going live (to iron out any environment-specific bugs).
Post-Release Monitoring: After deployment, we’ll monitor logs and maybe use uptime monitoring.
If any error makes it to production that tests didn’t catch, we’ll write a new test for it (test-driven bug
fixing). We’ll also monitor performance (if using something like NewRelic or simple server metrics) to
catch any endpoints that are slow or resource-heavy.
Maintaining Test Data: As the domain model evolves (e.g. adding new fields), tests need to be
updated. We’ll keep tests up to date alongside code changes to avoid a situation where tests are
outdated and thus ignored. Using factories or central fixtures for data creation helps – you update
the factory with new field defaults once, and all tests start using the new structure.
Fixtures and Pre-seeded DB for Dev: For developer convenience, we may provide a pre-populated
SQLite DB with some scenario (similar to seeds) that developers can use to quickly see a running
game state. This isn't exactly testing, but helps manual testing. We also provide clear instructions for
resetting the environment (like a script to wipe and reseed the dev database) so testers can start
from a known state repeatedly.
By implementing this comprehensive QA strategy, we aim to deliver a stable and reliable TavernTAIls
experience, where features behave as expected and any future changes can be made with confidence due
to the safety net of tests. Quality is especially important because the presence of AI might mask subtle bugs
(it's easy to blame the AI for something that might actually be a code issue), so our tests and logging
attempt to distinguish AI quirks from actual regressions.
Roadmap & Phases
Development will proceed in phases, from a Minimum Viable Product (MVP) focusing on core gameplay and
infrastructure, to subsequent phases that add depth, integrations, and polish. Below is a high-level
roadmap, followed by detailed work packages that break down the implementation steps. Each phase
builds on the previous and has defined goals and deliverables.
MVP (Phase 0) – Timeline: ~1–3 weeks of development
Focus: Implement the fundamental features to support a basic solo campaign experience with
minimal AI-driven elements (mostly stubs).
•
•
•
•
•
•
•
•
•
•
•
23
Key deliverables: User auth and accounts, campaign CRUD, session (with one default session per
campaign), invite system (with friend requests minimal or deferred), character creation/import (basic
manual entry, possibly with a simple JSON import), document upload for core/flavor/hidden, basic
chat interface and dice roller, stub AI agents (perhaps a dummy narrator that echoes player input or
a fixed narrative), and the dev environment setup ( start-app.ps1 ).
Acceptance criteria: A single user can run a simple session: sign up, create a campaign, add a
character, and type actions to receive some form of narrative response (even if canned). They can roll
dice and see results. They can invite a second user to join and see that user’s messages. Core/Flavor
document upload works (e.g. upload a map image as flavor and both users can see it), and hidden
docs remain only visible to host. The application runs without obvious errors through this flow. Basic
safety and auth checks in place.
Phase 1 – Timeline: ~4–8 weeks
Focus: Enhance the gameplay experience and introduce initial integrations and AI functionalities.
Key deliverables: Integrate Beyond20 for external dice, implement real AI logic for at least the
Narrator agent (maybe using a cheap model or a rules-based approach) to make the story
generation more dynamic, introduce background job processing (so AI calls and image generation
don’t block), add the friend system fully (so you can add friends and invite them easily), improve the
campaign lobby UI (list of campaigns, invite management), implement the PDF character import (so
users can import a D&D character sheet PDF), and set up WebSocket scaling with Redis (to handle
multiple clients robustly). Possibly also implement the turn management and asynchronous
notifications in this phase.
Acceptance criteria: Two or more users can conduct a richer session: the AI GM responds with
dynamic narrative (not just echoing) to their actions, dice rolls can be made from D&D Beyond
through Beyond20 into the session, friend invites work (you can friend someone and then invite “by
friend” instead of email), and the UI has a proper campaign selection screen rather than needing to
input campaign IDs or such. The system can run with multiple users connected concurrently without
mixing up data. Basic image generation could be introduced here as well (maybe one provider
integrated and ability to generate one image). Tests and CI fully running for these features.
Phase 2 – Timeline: ~8–16 weeks
Focus: Expansion and refinement of features, scaling considerations, and preparing for a wider
release.
Key deliverables: Fully implement D&D Beyond syncing via token (continuous sync of character
stats), add the AI Image generation feature with multiple style options, implement semantic search
for documents (embedding and vector DB integration) to improve AI context recall, enhance the DM
tools (allow the host to do more, like fudge rolls or reveal info easily), refine agent orchestration and
add more nuance (like NPC agent actually generating dialogue, Storyboard agent maintaining quest
logs), and improve the editor for Hidden docs (possibly a better UI to write longer notes or story
outlines within the app). Additionally, at this stage we address any remaining security or
performance issues, set up a production-ready deployment (Docker/K8s), and polish the UI/UX
(responsiveness, accessibility, bug fixes from feedback).
Acceptance criteria: The AI-driven gameplay feels coherent for at least short stories: e.g. the AI
doesn’t easily contradict itself thanks to semantic memory, images generated add value (players can
see scene illustrations), and the host has fine control to steer the story if needed. A player linking
their D&D Beyond account sees their character update after a level-up within a few minutes. The
system can handle a larger group (maybe 4-5 players) in a session reasonably well. Most importantly,
•
•
24
user feedback from earlier phases has been incorporated (e.g. if users found something confusing,
it’s reworked by now). The app is ready for an alpha release to a friendly audience.
The above phases are guidelines; actual development may adjust them based on what’s learned along the
way. After Phase 2, additional phases would likely focus on content/community features, mobile app
packaging (if desired), or supporting more game systems.
Detailed Work Packages
To implement the roadmap, we break the work into actionable packages. Each package can be seen as a
“story” or epic that delivers a coherent set of features. Below are the major work packages, with scope,
deliverables, acceptance criteria, estimates, dependencies, and risks:
Core Platform – Auth & Accounts, Friends
Scope: Implement robust user authentication (signup, login) with JWT tokens, and basic account
management including a friends system for social connectivity. Also, include user settings like
storing an optional D&D Beyond token for later integration.
Deliverables:
Database tables: users (with fields for email, password_hash, display_name, etc.) and
friends (to track friend relationships or friend requests). Migrations for these.
Backend endpoints:
POST /player/signup – creates a new user (in dev, returns verification token or autoverifies for simplicity).
POST /player/login – returns JWT (and refresh token if applicable).
GET /player/me – returns current user profile info (requires auth).
POST /player/friends – send a friend request (or accept one, possibly by including an
action in payload or separate endpoint).
GET /player/friends – list current friends and pending requests.
Possibly also an endpoint to revoke friend (unfriend) or to cancel a request.
Password hashing setup and token generation (likely using PyJWT or FastAPI’s security
utilities).
Frontend pages: Signup page, Login page (with form validation, error display), and a simple
Account or Friends management UI (could be a section in the dashboard where you see
friend requests and a form to add friend by username/email).
Basic email sending for verification (optional for MVP, could be just console log a verification
link token).
Tests: unit tests for auth (correct error on wrong password, etc.), integration tests for full
signup/login flow and friend request flow (two users friending each other).
Acceptance Criteria:
A new user can register an account. If email verification is simulated, they can retrieve the
verification token from logs and verify (or in dev, auto-verify). They can then log in with their
credentials and get a token to access protected endpoints.
Login failures (wrong password) return appropriate errors (without revealing too much, like
“incorrect credentials” generic message).
Auth token must be present to access game features; e.g., if you call GET /campaigns
without a token, you get 401 Unauthorized.
1.
2.
3.
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
4.
◦
◦
◦
25
Users can send friend requests by specifying a valid identifier (username or email) of an
existing user. The target user can see a pending friend request (via GET /player/friends
or maybe a real-time notification if online) and accept it. Once accepted, both appear in each
other’s friend lists.
The system prevents duplicate friend entries and doesn’t allow sending multiple pending
requests to the same user. Also, you cannot friend yourself.
Proper authorization: user A cannot accept a friend request on behalf of user B or see B’s
friends, etc.
(If refresh tokens implemented) The refresh flow works: access token expires (in a short time
set for test), and using refresh yields a new token. Revocation (logout) works, meaning
refresh token can be invalidated.
Sensitive data like passwords never travel or store in plaintext.
Estimated Effort: 3–5 days.
Dependencies: None on other packages (this is foundational). Just requires project scaffolding to be
in place. Will be used by nearly all subsequent packages.
Risks: Handling of authentication must be correct to avoid security issues. Also, building a friends
system could get complex if we consider edge cases (mutual confirmation, etc.), but we can simplify
by auto-accepting or just storing requests in one table. Another risk is ensuring that adding friends
by identifier can’t be abused to enumerate users (we might only allow by exact email or a unique
friend code to avoid exposing if a certain email is registered). We should also prepare for spam (rate
limit friend requests).
Campaigns & Sessions (Campaign CRUD & Membership)
Scope: Enable creation and management of campaigns, and handle inviting users to campaigns and
joining (membership flow). Essentially, this covers the campaign lifecycle and linking users to
campaigns (as players or GM). Also covers basic session creation – for MVP, the first session might be
created automatically with the campaign.
Deliverables:
Database: campaigns table, sessions table, invites table, and possibly a join table
campaign_members (or we derive membership from invites accepted). Fields as described
in Data Model. Include migrations.
Backend endpoints:
POST /campaigns – create a new campaign (requires auth). Body includes campaign
name, optional description. Response includes new campaign ID.
GET /campaigns – list campaigns user is part of (either as host or accepted player).
GET /campaigns/{id} – get details of a campaign (if user is member or invited). Could
include list of members (names and characters) and basic info.
PUT /campaigns/{id} – update campaign info (only host allowed), e.g. rename or archive
flag.
POST /campaigns/{id}/invite – invite a user to the campaign. Body might include
user_identifier (email or username) and min_level . This creates an invite entry
and triggers a notification.
Possibly GET /campaigns/{id}/invites – list pending invites (for host to see who’s
invited).
◦
◦
◦
◦
◦
5.
6.
7.
8.
9.
10.
◦
◦
◦
◦
◦
◦
◦
◦
26
POST /campaigns/{id}/join – accept an invite. Body includes character selection
(character_id or character data for new character). This will validate the invite and level
requirement, create campaign membership (and possibly mark invite as accepted or delete
it).
WebSocket or polling for campaign events: we might have the WS at /campaigns/{id}/ws
to cover real-time aspects, but membership changes can also be conveyed via API responses
for now.
POST /campaigns/{id}/sessions – create a new session in the campaign (for future
use). For MVP, not heavily used, but implement minimal for data consistency (or skip and
assume one session equals campaign).
Frontend UI:
Campaigns Dashboard: a page that shows “My Campaigns” (cards or list with campaign
name, maybe small info, and an option to open or manage). Also a “New Campaign” button
opening a form (campaign name).
Campaign View: once a campaign is opened, before entering the actual game session,
maybe a lobby view that shows campaign info, list of players (with their characters once
joined), and pending invites. Host sees controls to invite new players (input friend name or
email + level requirement), and to start the session (if not auto-start). Players who are not
host might see their character slot (choose which character or create one if needed).
If we do “session = campaign” for MVP, the campaign view might directly show the session UI.
But likely we have at least a stage to pick/assign character if invite required it.
Some visual indicator for host vs players in the campaign member list.
Email/Notification for invite: sending an email to the invited email with a link (if user not
registered, link invites them to sign up and auto-join; if registered, link maybe just directs to
login and then join page). We might implement a simple token in the invite link to identify it.
Tests: integration test for full invite flow – host invites, invitee accepts, ensure membership
created and appropriate limitations (like cannot accept twice, etc.). Test campaign creation
and listing – user only sees their campaigns. Test that non-members cannot access campaign
data (e.g. someone else’s campaign returns 403).
Acceptance Criteria:
A logged-in user can create a campaign. After creation, it appears in their campaigns list, and
they are marked as the host/GM.
The host can invite another user by email or username. If the invitee is an existing user, that
user when logging in can see a notification or listing of the invite (or at least can accept it via
a provided link or an invites page). If the invitee is not yet a user, an account can be created
via the invite link and after registration they are placed into the campaign. (For MVP, it’s
acceptable if we only support inviting existing users and handle the new user case later or
simply via email link requiring signup then manual join with code).
The invite can specify a minimum character level, and the system enforces that on acceptance
– e.g., if invite requires level 5 and the user tries to join with a level 3 character, it should
prompt that they need a higher-level character (or create a new one at required level if
allowed).
Upon accepting an invite, the user becomes a member of the campaign. They can then access
the campaign’s session (chat, docs, etc.). The host sees that the user joined, and their selected
character.
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
11.
◦
◦
◦
◦
27
Membership enforcement: only members (or invited users) can connect to a session’s
WebSocket or retrieve its messages/docs. If a user who isn’t part of campaign X tries to access
it (via API or UI), they get denied.
A host can remove a member (if implemented). At minimum, if a user leaves on their own, we
handle that gracefully (maybe a simple endpoint to leave campaign).
Campaign editing: host can rename or archive a campaign. Archiving would exclude it from
active list (perhaps via GET filter). Non-host cannot do those actions.
Session creation: if multiple sessions were to be used, host can create one, but likely we skip
detailed multi-session UI in MVP. Possibly automatically create “Session 1” on campaign
create. The acceptance here is that the data model allows expansion, but functionality wise
players just enter the default session.
Real-time or near-real-time: if host invites while both host and invitee are online, the invitee
should see it without a full refresh (we might not fully implement that push in MVP, maybe
just rely on page reload or an invites page).
Estimated Effort: 1–2 weeks (this is a broad feature touching UI, backend, and email).
Dependencies: Core Platform (auth) must be in place. Character Service (next package) is closely
linked because invite acceptance ties in character selection. Also Session Documents (for the
campaign context) but that can be parallel.
Risks: Handling the invite acceptance could get tricky (especially with linking to character creation).
We have to ensure no edge case where a campaign’s hidden info leaks to a not-yet-member. Also
sending emails or external communication can be error-prone (ensure not to send to wrong address
or include sensitive info in invite links). We should confirm whether to allow cross-user friend invites
only or freeform email invites – the latter introduces more complexity (we might do it but keep it
simple). There’s also a risk of orphaned invites (user never accepts) – not a big problem but maybe
provide a way to cancel. Access control mistakes here could open data to non-members, so must test
thoroughly.
Character Service & Import Pipeline
Scope: Provide functionality for players to create and manage characters, including importing from
external sources (initially via file or copy-paste). This includes the backend logic for parsing imports
and storing character data, and the frontend UI for character creation and selection.
Deliverables:
Database: characters table migration (owner_id, campaign_id (nullable), name, level,
class, race, stats JSON, etc.). Possibly a separate table for abilities or inventory, but likely store
as JSON for MVP for flexibility.
Backend endpoints:
POST /characters – create a new character. The payload can handle two modes: manual
create (explicit fields like name, class, etc.) or import (with a file or large text blob). We might
separate the import to a different endpoint for clarity, e.g. POST /characters/import
accepting a file upload or JSON payload. For now, one endpoint could handle both by contenttype (multipart for file, json for direct).
GET /characters – list current user’s characters (optionally filter out ones currently in
campaigns if we want to avoid duplicates in selection UI).
GET /characters/{id} – get details of a specific character (if the user owns it, or if it’s in
a campaign the user is GM of perhaps).
◦
◦
◦
◦
◦
12.
13.
14.
15.
16.
17.
◦
◦
◦
◦
◦
28
PUT /characters/{id} – update a character (e.g. after editing or leveling up).
Potentially an endpoint to facilitate import parsing, e.g. POST /characters/parse that
returns parsed data without saving, but this could be part of the main import flow where the
UI gets back the parsed results to confirm.
If we implement token-based D&D Beyond sync in Phase 2, an endpoint to fetch from D&D
Beyond, but for now, out of scope.
Character import logic:
Implementation of parsing for D&D Beyond JSON: If D&D Beyond offers JSON (like from their
API or copy), we map fields from that JSON to our schema. Possibly provide a sample and test
it.
Implementation of PDF parsing: Use PyMuPDF to extract text. Develop heuristic patterns
(regex) to find stat block (STR, DEX, etc.), proficiency bonus, saving throws, HP, etc. This will be
imperfect, so design it to not crash if something isn’t found. Perhaps return partial data and a
list of fields not found.
Possibly support simple text import from other formats (as stretch goal, maybe not needed
immediately).
Provide a mechanism for user to correct or fill missing info after import: e.g. the UI could
show an edit form pre-filled with whatever was parsed, so they can adjust and save.
Frontend UI:
Character Creator Form: A page or modal where a user can input character details manually.
At least name, level, and maybe a few key stats. We might not build a full D&D sheet UI (that’s
a lot), but enough for demonstration (maybe an "Ability Scores" section, and a text area for
other info).
Import Interface: An option to upload a PDF or paste content. For PDF upload, user selects
file and we call import endpoint, then show the parsed results for confirmation. For JSON
paste, similarly.
Character List: In the user’s profile or a modal in campaign invite acceptance, list their
characters with basic info (name, level, maybe avatar). Possibly allow deleting a character not
in use.
Invite Acceptance UI: When accepting an invite (if done via web UI), if the user has eligible
characters (>= required level), present a dropdown to choose one. Also allow creating a new
character on the spot (with the above form) if they prefer. If creating new via acceptance flow,
ideally after creation it auto-selects that one to join.
Character Sheet View: In the campaign session, players should be able to view their own
character stats (and GM to view all). For MVP, maybe a simple modal or sidebar that shows
the character info fields. It can be read-only for others’ characters unless GM editing. (Actual
editing likely outside session for now).
Tests:
Unit test the parser functions with sample inputs (one for JSON import if available, one for a
sample PDF text). Ensure key fields are correctly parsed (e.g. if PDF sample with STR 15, we
get str:15).
Integration test: create character via API, retrieve it, update it. Import test if possible (maybe
feed a known JSON to the import endpoint and verify result fields).
Integration test: campaign invite acceptance with character selection – simulate via API: user
B accepts invite with a given character id and ensure membership created and that character
is now tied to campaign.
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
29
Acceptance Criteria:
Users can create a new character manually: after filling required fields and submitting, the
character appears in their list. If they navigate away or refresh, the character persists (stored
in DB).
Users can import a character from a given source: e.g., given a provided example D&D
Beyond JSON, the system creates a character with matching attributes (name, level, stats,
etc.). Or given an example official 5e character sheet PDF, it fills in the main fields. If some
information can’t be parsed, it’s either left blank for the user to fill or captured in a generic
notes field. Import should not produce incorrect data in fields (better to leave blank than
wrong).
On invite acceptance, if a min level is required, the UI/API enforces it. For example, if none of
the user’s characters meet the level, it either prevents joining until they create one of
sufficient level or it allows creating a new one with that level. This decision will be
implemented accordingly (maybe simplest: allow creation of a character at the required level
as part of acceptance).
A user cannot access another user’s characters except through campaigns: e.g., user A cannot
call the API for user B’s character id and retrieve it (should get 403 or not found). The GM of a
campaign can view characters of players in their campaign via campaign endpoints (or
perhaps via an authorized route like GET campaign/{id}/characters if we add that).
The character data structure supports the needed game mechanics: at least the attributes
and level. For future integration, we store enough info (like if implementing dice with mods,
we need ability scores and proficiency maybe). But acceptance is that, for now, PencilPusher
can retrieve ability mods if needed from this data.
No sensitive data in characters (shouldn’t be, they’re fictional) except user id references which
are internal.
If a character is currently in a campaign, the system might lock some edits (maybe don’t allow
deleting or drastically altering stats mid-game through the character API without GM actions).
For MVP, we might keep it simple and just not allow deletion if tied to active campaign.
Estimated Effort: 1–3 weeks, depending on complexity of import (the parsing might take significant
time to refine).
Dependencies: Core platform (for user accounts), Campaigns/Invites (for linking characters to
invites). Not heavily dependent on Session Docs, except if we considered storing character sheets as
docs (we decided to store structured in DB instead).
Risks: PDF parsing is error-prone; we might spend a lot of time and still not cover all cases. We
mitigate by focusing on a narrow format initially. Also, there’s a slight risk in terms of legality if we
parse content from copyrighted sources – but since it’s user-provided data and we’re not
redistributing, it should be fine (just mention we assume they have rights to the data they import).
Data model flexibility vs usability: storing all in JSON makes it easy to ingest varied data but harder to
query (e.g. searching characters by stat). But that’s an acceptable trade-off for now. Another risk:
time – if import is too hard, fallback to requiring manual entry for MVP to not blow the timeline. Also
need to ensure that imported data doesn’t break our UI if something unexpected (e.g. extremely
long inventory list – maybe just truncate or scroll).
Dice Engine & Beyond20 Integration
18.
◦
◦
◦
◦
◦
◦
◦
19.
20.
21.
22.
30
Scope: Develop the PencilPusher dice rolling engine for in-app rolls, and integrate with the
Beyond20 extension to handle dice rolls coming from external character sheets (like D&D Beyond).
Ensure consistent treatment of all rolls and logging of outcomes.
Deliverables:
Backend logic: A module or class (within an agent or separate util) to parse and evaluate dice
expressions. Likely support expressions like:
NdM + K (e.g. 2d6+3 ),
Possibly advantage/disadvantage (maybe beyond20 or user might specify something like
2d20kh1+5 for "keep highest 1", but we can limit scope if needed),
We should also handle simple ones like d20 meaning 1d20 .
The logic should produce not just the final result but a breakdown (for transparency). E.g.
2d6+3 -> rolls [4, 2] = sum 6, +3 = 9 total. We can format this for display.
Persist roll results: either as messages (with a special type and maybe JSON payload for
breakdown) or in a rolls table linked to the message. Probably easier: create a Message of
type "roll_result" with content like "Alice rolled 9 (2d6+3)" and store details in JSON field if
needed.
Endpoints:
POST /campaigns/{id}/rolls – for internal use when a player clicks roll in UI. Body:
{"formula": "1d20+5", "character_id": 12 (optional)} . The server resolves the
roll (considering if a character ID is given, maybe adjust or just use it for logging) and returns
the result. Additionally, it broadcasts the result to the session’s WebSocket so all players see it.
POST /integrations/beyond20/roll – an endpoint to receive rolls from Beyond20 .
The exact payload depends on Beyond20’s config: possibly it sends something like a JSON
with the roll result and description. We may need the user’s token in the request to identify
them (Beyond20 can be configured to include a custom token or we might require it to call an
authenticated endpoint). Alternatively, we might have the user run a small local forwarding
that attaches their token – this is a bit tricky. For MVP, perhaps accept an unauthenticated
request if it has a secret that we embed in the Beyond20 config. For example, when a user
wants to integrate Beyond20, we show them a URL with a unique token (mapping to their
session/user) to put in Beyond20. The endpoint then verifies that token and maps to the user/
campaign.
The Beyond20 endpoint will then take the incoming roll (which might already have total and
breakdown, since Beyond20 knows the dice results and adds mods) and treat it the same as
an in-app roll: log it and broadcast. If needed, we might recompute to verify, but probably
trust it.
Possibly an endpoint to configure beyond20: maybe not needed, just documentation.
Frontend UI:
In chat or UI, a way to roll dice. Options: a simple text command (we can allow users to type "/
roll 2d6+3" in chat which the backend interprets). And/or a dice icon button that opens a
small dialog to input the formula or select common dice (d20, d6, etc.) and a field for modifier.
For MVP, a text input might suffice if documented. We can also provide quick buttons for d20
(since that’s most used).
Display of roll results: When a roll occurs, show it in the chat log. Possibly with a different
style (e.g. italic smaller text or an embedded result box). Include who rolled, what they rolled,
and the outcome. If the roll had significance (like “success” or “fail” if target known), that’s not
determined by PencilPusher – that’s the game logic to interpret. So here it’s just raw results.
23.
24.
◦
◦
◦
◦
◦
◦
◦
◦
◦ 15
◦
◦
◦
◦
◦
31
Ensure that if multiple players roll simultaneously, results don’t conflict and all appear
properly.
Some UI element to integrate beyond20: we might have a section in user settings: “Beyond20
Integration: use this URL in your Beyond20 config: http://<server>/integrations/
beyond20/roll?token=XYZ ”. That token ties the incoming roll to their account. Or if we do
by session, could embed campaign ID too. We will provide instructions for users to set it up.
Possibly also handle CORS or require them to run a local forward if needed (Beyond20 can
send to localhost; if our app not local, might be an issue unless using HTTPS and a publicly
accessible address). Document accordingly (maybe in README or a wiki page rather than UI if
complex).
Tests:
Unit test the dice parser with various inputs (including edge cases like 0d10, negative
modifiers, etc.) to ensure it calculates correctly.
Integration test: simulate a roll via API (POST /rolls) and check that it appears in message list
with correct data.
If possible, simulate a Beyond20 call: call the integrate endpoint with a sample payload and
ensure it produces a similar result. Might need to pre-create the token mapping in test or
adjust method if our integration approach is stateless (like maybe it includes campaign and
user email in payload, which isn’t secure unless tokened). Possibly simpler: require user to be
logged in on browser, but Beyond20 is outside the browser context, so likely a token param
approach.
Test unauthorized roll attempts: e.g. user A trying to roll in campaign B where they aren’t a
member (should be blocked).
Acceptance Criteria:
Players can perform dice rolls within TavernTAIls easily and see the results shared with the
group. For example, if Alice types "/roll 1d20+5", everyone sees a message "Alice rolls 1d20+5
→ 14". The random outcome is generated by the server, and each player’s view is consistent.
The dice roller correctly calculates results for typical expressions (d20, 2d6+3, etc.), and the
results fall within expected ranges (no off-by-one, and the distribution seems uniform
random on repeated tests).
If a dice roll is triggered by the AI (say the Scene agent requests a roll), the system can either
roll automatically and show something like "GM requests a roll: [roll outcome]" or prompt a
player. For MVP, we might simply have the GM agent auto-roll and present it. But ensure that
path works: e.g., orchestrator can call PencilPusher and insert the result in narrative (tested
as part of agent integration).
Beyond20 integration: A user with a D&D Beyond character sheet and the Beyond20
extension can click a skill or attack on D&D Beyond, and the roll result appears in the
TavernTAIls session as if they rolled it there. That means our endpoint received the data and
broadcasted it. For example, if Bob has a character on D&D Beyond with +7 to hit, and he
clicks an attack, players might see "Bob rolls 1d20+7 → 18". (We likely won’t differentiate that
it came from Beyond20, though we could mark it “(via D&D Beyond)” optionally.)
The Beyond20 integration should be secure: only authorized events go through. If using a
token in URL, an attacker without that token cannot spam our endpoint effectively (and even
with token, it only affects that user’s campaign). Also we handle potential CORS or CSRF
concerns if any (but since extension sends directly, CORS we can allow specifically Beyond20
requests).
◦
◦
◦
◦
◦
◦
◦
25.
◦
◦
◦
◦
◦
32
Performance: rolling should be fast (just computing some random numbers). Even if many
rolls happen, it’s a small computation. The server should handle say 100 roll requests in quick
succession (like someone spamming) without issue, aside from rate limiting if we impose.
Logging: All rolls are recorded in the campaign’s data (messages or roll logs) so that reloading
the page still shows them. They should be ordered correctly among other messages by
timestamp.
No cheating: The roll outcomes are generated server-side with an unbiased PRNG. A user
shouldn’t be able to influence the result (besides specifying the formula). If using beyond20,
we assume the external roll is legit (if someone hacked their beyond20 to always send 20, we
can’t easily detect that without re-rolling ourselves; we might accept that risk or optionally
verify by also rolling and comparing – but likely unnecessary for cooperative game).
Estimated Effort: 3–5 days. (Implementing and testing the dice logic is straightforward; beyond20
integration might take more time due to needing to test with the extension and adjust for CORS or
network issues.)
Dependencies: Campaign & Session infrastructure (so we have a place to send roll events),
Character service (if we want to annotate rolls with character info, but not strictly needed to
implement basic rolling). WebSocket should be in place for broadcasting. Also depends on having
some understanding of beyond20’s mechanics (might require reading their docs).
Risks: The beyond20 part is somewhat external and could fail due to factors outside our control
(user misconfiguring, or if beyond20’s format changes). We mitigate by testing with current version
and providing clear setup instructions. Another risk: deciding how to authenticate beyond20 calls –
security vs convenience trade-off. We’ll likely include a secret token in the URL and validate it serverside. This token needs to map to the correct campaign and user; if the user is in multiple campaigns
concurrently, beyond20 doesn’t inherently know which campaign to target – we might assume one
active campaign per user at a time (like whichever they last had open, or provide separate endpoints
per campaign). Perhaps simplest: have the extension use the currently open TavernTAIls page’s URL
if possible. Actually, beyond20 can be configured with multiple URLs and you check a box which one
to send to. The user could set it to their local dev address for testing. For a hosted scenario, maybe
the extension can detect if our app’s tab is open and use that (beyond20 does that for known VTTs).
If we get beyond20 to treat us like a custom VTT, we have to manually add – likely user sets a custom
URL. We document this process thoroughly.
Another risk: Dealing with unusual dice expressions from beyond20 – beyond basic ones (like some
systems have exploding dice, etc.). We might ignore those for now or handle a subset.
AI Agents Framework (Stubs & Orchestration)
Scope: Establish the agent-based architecture with minimal implementations (stubs) for each of the
main agents and the GM orchestrator. Define the interfaces (I/O contracts) and set up the internal
API or function calls between orchestrator and agents. This sets the stage for plugging in actual AI in
later steps, but initially the agents can produce canned or rule-based responses for testing.
Deliverables:
Code structure: Create server/agents/ directory with modules for each agent
(narrative.py, scene.py, npc.py, storyboard.py, notes.py, image.py, etc.). Each module might
contain: input/output Pydantic models for that agent’s main function, and a FastAPI router if
we want to expose endpoints (for testing or if we considered microservice separation;
possibly not expose externally in MVP, keep internal).
◦
◦
◦
26.
27.
28.
29.
30.
31.
◦
33
The GM Orchestrator: Implement a function (maybe in a gm.py or as part of narrative.py if
GM is considered central) that coordinates calls to others. This could be done as a class or just
a function that takes a user action (or event) and returns a result event. For now, it will call
stub agent functions synchronously.
Stub logic for each agent:
Narrator: Could simply take the player’s last action and return a generic response, e.g. "You
proceed with the action." or echo the action like, "You said: <action>". This shows the pipeline
without needing AI yet.
Writer: Possibly returns a one-line "next plot point" like "The story continues..." stub.
Scene: Could parse the text for keywords "attack" or "stealth" and if found, emit a roll_request
event for demonstration. Otherwise returns no event.
NPC: We might not call it in MVP stub, but if called, it could return a simple line of NPC
dialogue or an empty result.
Storyboard: Could maintain an in-memory dict of completed events just for structure, or just
do nothing in stub.
Notes: Could append to an in-memory log whenever called to simulate note-taking, or just
acknowledge.
Image: Stub could immediately return a placeholder image URL (like a static "no_image.png"
or some generated pattern) to simulate an image. Or it could not be invoked until Phase 2
when integrated.
Each stub should adhere to the I/O format we set (type, payload, etc.). Possibly define a base
class or constants for event types (narration, roll_request, etc.).
Integration with the session flow: Modify the chat message handling to involve the
orchestrator. For example, when a player sends a message (action) that is marked as a game
action (maybe everything is treated as an action for now), the backend will pass it to the GM
orchestrator, get back events, and then broadcast those events (e.g. a narration or roll
request) to the session. The orchestrator can also directly insert into the DB logs if needed.
Background worker setup: Even if we stub, we want to set up a Celery or RQ queue to prepare
for real AI calls. Install and configure Celery (with Redis broker). Start a worker process in dev
environment via start-app.ps1 . Initially, we might not put stub calls in queue (since they
are fast), but we lay groundwork (like defining a tasks.py with a Celery app and a sample
task, maybe hooking the Image generation stub to always use a background task to
demonstrate flow).
Testing tools: Provide a simple mechanism to test agents in isolation. Could be a Python script
or API endpoints: e.g. an endpoint POST /agents/narrator/debug that takes some input
and returns stub output. This isn’t user-facing, but helps dev/test. (Alternatively, rely on unit
tests calling the functions.)
Tests:
Unit tests for orchestrator: feed it a sample state and player action, ensure it returns a
Narration event type with content (from stub). If action contains "attack", ensure orchestrator
triggers Scene which triggers a Roll event. We might have to simulate multiple agent calls:
test that orchestrator collects outputs from Writer and Narrator properly.
Unit tests for each agent stub: Narrator returns expected output format given input, Scene
triggers on keywords, etc.
Integration test: simulate a user sending a chat message "attack the orc", then verify that in
the messages or events that come out, we see a narration stub plus a roll_request stub (if
that’s how stubs behave). Essentially verifying the end-to-end pipeline through orchestrator.
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
34
Acceptance Criteria:
The codebase now includes a clear modular structure for agents, and the GM orchestrator
logic is implemented to coordinate them.
When the system is running in stub mode, and a player enters an action (via chat), the
backend processes it through the orchestrator and returns one or more events: e.g., a
Narration (like "The action is noted.") possibly followed by a roll request (if triggered). These
events appear to the player in the chat UI appropriately.
The transition from one user message to AI response is automatic – a player doesn’t have to
manually click anything to get the AI reply. After a slight delay (maybe none for stubs), the
reply shows up as if from the GM/Narrator.
The stub behavior is simplistic but deterministic, which is fine – this phase is about proving
the architecture. For instance, maybe we decide: Narrator just echoes or acknowledges,
Scene agent triggers a dice roll if the word "roll" or "attack" in input, etc. So if a player types "I
attack the goblin", the orchestrator calls Scene -> sees "attack", returns roll_request ->
orchestrator calls PencilPusher (or just directly handles because stub) -> gets a result -> calls
Narrator with maybe context (result of roll: e.g., success or fail) -> Narrator returns "You hit
the goblin dealing X damage." Or more simply, orchestrator might itself handle "if roll success
then narrate X, else Y". But maybe for stub we won't simulate success/fail logic deeply. The
key is that multiple agents can contribute and GM composes an outcome.
The agent I/O contract is respected everywhere. If we define, say, an AgentOutput model
with fields type/payload, all agents use it. That means when we later replace stub logic with
real AI calls, we follow the same interface.
The background queue (Celery/RQ) is up and running (tested by maybe an example task or
the image agent stub using it). This means heavy operations can be offloaded. For stub, we
might not need it but ensure it’s ready (e.g., the pipeline for image agent calls
task_generate_image.delay(prompt) and that just immediately returns a stub result in
dev). We confirm the worker can pick up tasks (log output shows it processing jobs).
Documentation: internal documentation (maybe an updated AGENTS.md) listing the roles
and current stub behaviors, and how to call the orchestrator from code.
Estimated Effort: 2–4 weeks (because designing and implementing the architecture is significant,
even if stubs are simple. Coordination between multiple parts, ensuring threads/async don’t conflict,
etc.). This is a critical foundational step.
Dependencies: Depends on previous pieces: we need the messaging system and possibly the dice
engine integrated to fully test orchestrator in context. But in parallel, this can be developed since
stubs don’t need external integration complete (just simulate calls). Still, for full test, hooking into
the chat flow is needed which depends on chat backend (package 7). We might develop stubs and
orchestrator alongside or slightly before finalizing chat turn system. Also depends on some available
vector or docs if those agents would use them (not really for stubs).
Risks: This is the core AI architecture; a design flaw here could be hard to change later. We have to
carefully think through how agents communicate. Too tight coupling and it’s inflexible; too loose and
it’s hard to implement. We mitigate by following the design laid out (with GM orchestrator
controlling flow) and by keeping interfaces simple (JSON in/out). Another risk is complexity: ensuring
that orchestrator doesn’t become unmanageably complex even with just stubs. We should
implement in a straightforward synchronous way first, then later introduce concurrency or async as
needed. Perhaps initially orchestrator calls one agent after another sequentially (e.g. Writer ->
Narrator -> Scene), which is fine.
Performance risk: calling multiple agents will later cost time (if all call external APIs). The plan is to
32.
◦
◦
◦
◦
◦
◦
◦
33.
34.
35.
35
eventually do some in parallel via background tasks. But for stub, performance is fine. We just
should design in a way that we can swap synchronous calls with async tasks easily.
Also, since we plan to use actual AI calls later, ensure that the orchestrator can handle variability:
e.g., an agent might not return any meaningful output (like the Writer might say "No change"),
orchestrator should continue gracefully.
Testing risk: with multiple moving parts, writing deterministic tests is tricky. We’ll need to control
stub outputs. That should be okay if stubs are deterministic functions. If orchestrator uses random
(like if stub calls dice), we’ll control that via seeding or injection in tests.
Session Documents Feature (Upload/Download & Permissions)
Scope: Implement the ability for users to upload and retrieve session documents (Core, Flavor,
Hidden) and enforce the visibility rules around them. Also provide UI to manage these documents
during a campaign.
Deliverables:
Backend:
Ensure documents table and file storage structure are set up (some of this might have been
planned in earlier architecture, but now implement).
Endpoints:
POST /campaigns/{id}/documents – handle file upload. Use FastAPI ’s
UploadFile for receiving files. Save the file to data/campaign_{id}/ directory with
an appropriate subfolder or prefix for type if needed. Save a record in DB with
metadata: type, original filename, uploader, timestamp, etc. If the file is text (like
maybe a .txt or .md), we could treat it as text and even generate an embedding if we
had that online, but likely skip embedding here (phase 2).
GET /campaigns/{id}/documents – return list of documents metadata in that
campaign, filtering out Hidden docs if the requester is not the host. Perhaps support
query param type=core/flavor for convenience.
GET /documents/{id} – download endpoint. This checks that the user has access
to that document (they belong to the campaign and either it’s not hidden or they are
host). If okay, returns the file (set proper headers). Could also implement a secure
redirect if using cloud storage (like generate presigned URL and redirect). For MVP,
serve from local disk through Python.
Possibly DELETE /documents/{id} or an endpoint to update metadata (like
rename or reassign type). MVP might not need those; host could just re-upload if
needed.
Permission enforcement: Hidden docs – only host and possibly designated co-GMs can see.
Flavor and Core – all campaign members can see/download. Possibly require login even for
flavor if share link leaked (we can tie the download to auth). Audit: maybe log when a hidden
doc is downloaded by host for transparency (though if just one host, not needed, but if
multiple hosts concept, then you’d want to know who accessed secret info).
Large file handling: set a max file size and return 413 if exceeded. Possibly integrate a library
or mechanism to not load entire file in memory (UploadFile gives a Spooled file, so fine).
Frontend UI:
In the campaign session interface (or a campaign management tab), present the document
list. Perhaps a tab control: "Documents". Within that, segmented by Core, Flavor for players;
36.
37.
38.
◦
◦
◦
▪
▪
▪
▪
◦
◦
◦
◦
36
host sees Core, Flavor, and Hidden sections. Each section lists documents by name, maybe
with an icon or file type indicator.
Upload interface: host gets buttons to upload Core and Hidden docs; players maybe only get
to upload Flavor (depending on our policy). For MVP, likely allow players to upload flavor docs
(like share their own notes or images), and only host can upload core (like official map or
rules doc) or hidden.
Use an <input type=file> element and on change, call the API (with the right type
parameter). Possibly show a progress bar if needed (for very large files, but with small limit,
skip). After upload, the list updates showing the new file.
Clicking a document (or a download icon next to it) triggers a download. On web, that might
open a new tab or directly download depending on file type. For images, we might do fancy
display: maybe clicking an image doc opens a lightbox to view it larger in-app. For a PDF,
clicking could either download or open in new tab if we set content-disposition accordingly.
UI for versioning if implemented (MVP might not have explicit versioning UI aside from
maybe showing an upload date). Possibly skip version control features now except storing it
behind scenes.
Basic styling for document list (perhaps file name, maybe a short description if we allow
adding one, and who uploaded it). For core docs, who uploaded might be host usually; for
flavor, show uploader name to give credit. Hidden obviously only visible to host.
Integration with Agents: Possibly not in MVP, but note: core docs should be accessible to AI
(like if an agent wants to read them). We can handle that by having orchestrator load them
into state if needed or an agent could query via an internal call. But for now, this package is
mostly about file handling and UI.
Tests:
Integration test for upload: simulate a file upload (FastAPI TestClient can send files) as host
and as player. Check that host can upload all types, player uploading core/hidden is forbidden
or converted to flavor, etc. Check DB entry created and file exists on disk.
Test listing: host sees all docs including hidden; player sees only allowed ones.
Test download: host can download a hidden doc; a player trying to download the same
hidden doc gets 403. A player downloading a flavor doc they uploaded vs another player’s
flavor doc – both should be fine.
If versioning on update: test that uploading a new version either creates new doc entry or
updates existing with version bump and old still accessible if we decided that. But likely not
doing editing in MVP.
Acceptance Criteria:
Users can upload documents into their campaign and retrieve them successfully. For
example, the host can upload a PDF as a Core document (perhaps the campaign rulebook or
a map), and afterward all players see that file listed under Core and can download or view it.
If a player uploads a Flavor document (say an image or text snippet for flavor), all players
including the host see it under Flavor and can access it. This fosters collaborative worldbuilding.
Hidden documents uploaded by the host (like an outline of the story) do not appear for
players. Only the host sees them in the Hidden list. If a player somehow guesses a hidden
document ID/URL and tries to GET it, the server denies access. We effectively protect secret
info.
Document metadata: when listing, it provides enough info (at least filename and type). It
might also include who uploaded and upload date. Not critical, but helpful. Host likely knows
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
39.
◦
◦
◦
◦
37
what each hidden doc is but players might not, so naming matters. Perhaps enforce or
suggest meaningful names on upload (we might allow an optional title separate from file
name).
The storage works for at least moderate files (a few MBs). Trying a 5MB image or PDF should
succeed (assuming within our limit). Larger files beyond limit should produce a friendly error.
The server should not allow malicious files to break it: uploading something like a .exe
should just be treated as a binary file (we can allow any extension but no execution). Serving
it back should force download rather than execution. For certain types like images/PDF,
browsers handle them inline; other types would download. That’s fine.
Security: no path traversal (we use secure filename handling, e.g., ignoring directory
components of original filename). Files are stored in a campaign-specific folder to avoid
collisions or mixing data.
Clean up: if a campaign is deleted, currently we might not implement auto file deletion (but
could mention to clean up manually). That’s fine for MVP, though better to clean.
The UI updates in real-time or near real-time: if one user uploads a doc, others will see it
listed without full refresh (we might implement that by using the existing WebSocket: maybe
send a “doc_uploaded” event through WS so clients know to refresh the list or we simply rely
on the fact that for now mostly host uploads and then instruct players "hey refresh
documents list"). MVP can allow a manual refresh (like a refresh button or reloading page). In
Phase 2, we can refine for real-time update.
Estimated Effort: 1–2 weeks.
Dependencies: Depends on campaign membership for permissions (Campaigns package). Also
depends on the existence of a storage mechanism (if not done yet; likely straightforward to
implement). Not heavily dependent on others. Should be done after Auth and Campaign basics are
done.
Risks: File handling always has edge cases – e.g., different browsers might give different file
metadata, or if a user tries to upload two files with same name. We should either allow duplicate
names (store with unique IDs internally) or prompt. Simplest is to allow and maybe differentiate by
ID in storage. Also storing on disk has risk of filling server storage if abused; we rely on size limits
and perhaps later quotas. Another risk is malicious content in files (viruses) – we likely won’t scan
files in MVP beyond trusting users. For a closed test, okay; for public, might consider integrating an
antivirus scan or at least restrict file types.
Also, concurrency: what if two people upload at same time with same file name or same doc? We
might end up with two separate entries, which is fine (just ensure no filesystem conflict; using
unique IDs or temp names solves that).
Permissions risk: must double-check all routes to ensure hidden vs flavor vs core checks are correct.
Use role from JWT and campaign membership to validate on each relevant request.
Chat, Turn Queue & Notifications
Scope: Finalize the session chat functionality (persistent message log, ability to handle asynchronous
play), implement a turn queue system for structured turn-taking (especially in asynchronous mode),
and integrate basic notifications (email or in-app) to alert players of relevant events (like invites or
when it’s their turn).
Deliverables:
Backend:
◦
◦
◦
◦
◦
40.
41.
42.
43.
44.
45.
◦
38
Confirm messages table structure (if not already, migrate to have one with appropriate
columns: id, campaign_id, sender_id (nullable for system messages), content, type,
timestamp).
Endpoints:
GET /campaigns/{id}/messages – return the backlog of messages for that
session. We might implement pagination or just return the last N messages for
performance. Possibly allow a query param for since a certain ID to get recent ones.
This helps on initial load or if a user reconnects.
POST /campaigns/{id}/messages – post a new message to the session. This
could handle both player messages and system commands. E.g., if content starts with
"/", we might interpret it differently, but perhaps the orchestrator approach covers
commands. In general, this endpoint will create a new message in DB and broadcast it
via WebSocket to others. If the message represents a user action that should trigger
the AI, the backend would then call the orchestrator and generate further messages
(like narration) as a result. Possibly, we split the idea of a "player action" vs "chat
message" for clarity. But maybe simpler: any message can be picked up by
orchestrator if it's not marked as OOC (out-of-character). Could use a flag or
convention. For MVP, assume all messages from players go into the story flow and
trigger AI. (We might revisit if we want OOC chat separate).
WebSocket /campaigns/{id}/ws : the implementation should broadcast new
messages and events to connected clients. We might refine the WS protocol to not
only send chat messages but also separate event types (like a structured JSON for
"turn_change" events). Or we can send everything as a chat message for simplicity,
with system messages indicating turn changes. Perhaps mix: minimal custom events
for things that are easier out-of-band.
Turn management:
Keep track of whose turn it is in a session. We can store active_turn_user_id in
the Session table or manage it in memory / via an agent. To start, maybe maintain in
memory with fallback to DB if needed for persistence (persist on change).
Endpoints to manipulate turn:
POST /campaigns/{id}/turn/next – called by either the current turn user
(saying “I end my turn”) or GM to force turn advance. It will set the next user as active
(cycling through members list or a predefined initiative order if we have one). For MVP,
turn order might just follow the join order or a simple fixed round-robin. We can refine
if needed.
Possibly POST /campaigns/{id}/turn/order if we allow GM to set a custom
order (like after rolling initiative, GM can set the sequence). Could take an array of user
IDs to define turn sequence. MVP could skip and just use something basic.
The system should automatically broadcast turn changes. If using WS, maybe send a
special message or a chat system message like "It is now Alice's turn." Also the
frontend can highlight accordingly.
If asynchronous, might incorporate a timer or threshold for notifications (e.g., if
someone's been “on turn” for X hours and hasn’t acted, send them a reminder email;
but implementing that might be beyond MVP – maybe manual poke button by GM to
send a reminder).
Notifications:
Email sending for key events:
◦
◦
▪
▪
▪
◦
▪
▪
▪
▪
▪
▪
◦
▪
39
Invite email (already considered in Campaigns package).
Turn notification: when turn passes to a user, if that user is not currently connected via
WS (we can track connected sockets per user), then send an email: "Your turn in
campaign X." Possibly include last message or a link to jump in.
Possibly friend request emails or at least in-app (maybe skip email for friend, just
handle in UI).
Use a simple SMTP or email API for sending. We might integrate something like
FastAPI’s background tasks to send email after responses so it doesn’t slow user
actions. Or a Celery task for email send.
In-app notifications:
When user logs in, they can query invites (from earlier). If any pending invites or friend
requests, those should be shown (like a notification icon with count). Could implement
GET /player/notifications for invites and such. But due to time, maybe we just
incorporate invites into friend list or something.
For turns: the UI could highlight if it’s your turn via a banner or styling in the session.
That’s immediate via WS event.
Mentions: If someone types @Username in chat, we might catch that and if the
mentioned user is offline, send an email or push. But implementing mention detection
and notifications might be an enhancement for later, unless easy.
We should ensure emailing uses user’s email from signup, and have a config to disable
emails (for dev or if user opts out).
Possibly consolidate multiple events into one email if they happen close together to
avoid spamming (not likely in our scale right now).
Frontend:
Chat interface:
A chat log area (scrollable) showing messages. Each message should include sender
name (or "GM" or "System" for AI outputs or system notifications) and timestamp
perhaps. Possibly style system/AI messages differently (e.g. italics for narration,
colored name for GM).
Input box for typing messages. We might support basic markdown (the AI might
output markdown too). At least newlines or ** for bold. Could either allow raw
markdown or create a toolbar. Possibly out-of-scope to refine in MVP beyond plain text
and maybe newlines.
Sending message triggers the POST /messages call. We handle the response or rely
on WS echo to show it.
Auto-scroll to new messages unless user is scrolling up. Provide some indicator if new
messages come while scrolled up (like "New messages" button). Might skip fancy
behavior in MVP.
Display of dice results and system messages in the log as well. E.g. if a roll result event
comes, show "System: Bob rolled X." Possibly style that differently (e.g. small text).
Turn indicator:
Show somewhere whose turn it is. If it’s the user’s turn, highlight it (big "Your Turn"
notice). If not, show "Current turn: [Name]".
If user is GM, perhaps also show entire turn order (list of players in order, highlight
current). Could be a small sidebar or part of UI.
▪
▪
▪
▪
▪
▪
▪
▪
▪
▪
◦
◦
▪
▪
▪
▪
▪
◦
▪
▪
40
Provide a button for the current turn user to end their turn (which calls the next-turn
endpoint). For GM, maybe also a control to skip someone or reorder if needed (for
MVP maybe skip reorder UI).
If asynchronous, maybe also show how long the turn has been active (like "Alice’s turn
(2 days)" if someone is lagging – but this could be a later feature).
Presence: Possibly indicate online players in the session UI (like their name is green if
connected). We can track via WS connections and send an update event. If easy, do it; if not,
skip for now.
Invite & Friend notifications UI: If not done elsewhere, the main UI (maybe NavBar) could
have an icon if pending invites. Or just ensure when a user goes to campaigns page, any
campaign invites are shown (like a banner or a separate section "Invitations").
Email notifications opt-in: If we foresee need, allow user to toggle in settings "email me for
turns/invites". But maybe default on and they can unsubscribe via email link if too advanced
to build UI.
Tests:
Integration: simulate two users in a session via WebSocket test client (if possible) to ensure
that one’s message is broadcast to other. (Might not easily test WS in standard testing – could
do an async test with websockets library connecting to Uvicorn running, or simpler: test the
behind-the-scenes pub/sub by calling the message post endpoint and then directly checking
DB or a mocked WebSocket send function to see if it was called. Could monkeypatch the
broadcaster in tests.)
Test that messages persist: send a few messages, then call GET messages and see them.
Test turn logic: in a test, set up a campaign with 3 users, simulate calling next-turn and verify
that the active turn cycles correctly.
Test that a non-GM cannot force turn change (should they even have access? If we allow
current user to end, that’s okay, but not someone else’s turn unless GM).
Test notification triggers: possibly unit test a function that decides “should send email for turn
event?” by providing scenarios (user offline -> yes call email function, user online -> no). We
can simulate offline by e.g. no WS connection in record. If we maintain an in-memory map of
connected users, might expose that for test or allow injection.
We could test that our email sending function is called with correct content (by
monkeypatching a send_email function in tests).
Acceptance Criteria:
The chat system allows real-time communication between players and GM (and AI outputs
appear in it). If two users are in the same session, when one sends a message, the other sees
it almost immediately (through WS). If a user is offline, any messages that happened while
away are loaded via GET on reconnect (persistent log).
The chat log persists so that if you leave the session (or refresh) and come back, you can
scroll and see past messages/narration from earlier in the campaign. There might be a limit
or pagination, but at least the recent history is there.
Turn order is managed properly: The interface clearly indicates whose turn it is. Only that
player (or the GM) can signal to advance the turn. Once advanced, the next player is
highlighted. This ensures that in asynchronous mode, players know when they are expected
to act.
When it becomes a player’s turn and they are not currently active online, they receive a
notification email informing them that it’s their turn, with a link to the campaign. (We should
test this by having user disconnect then next-turn fired -> email should be sent).
▪
▪
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
46.
◦
◦
◦
◦
41
Similarly, when a player gets invited to a campaign, they receive an email invitation (if an
email was provided). And/or if they’re online, the UI updates to show an invite.
Basic friend request notification: maybe not email, but at least the next time the user logs in
or goes to friends page, they see the pending request.
The system handles asynchronous play gracefully: e.g., if Bob takes a day to respond on his
turn, others can still send out-of-character chat or discuss in chat (assuming we allow that) or
maybe they can’t if strictly turn-based? Usually in async, others might wait or discuss OOC.
Possibly players can still chat out-of-turn (just not progress story actions). We might allow
normal chat always, and just note turns for action-taking. That’s a nuance in design, but for
acceptance we might say: players can still type even off-turn (maybe to discuss strategy), but
the AI won’t respond until the turn-holder does something or GM advances. This may be
more a gameplay policy than technical. But no technical blocker should prevent sending
messages out of turn.
Presence indicator (if done): shows who is online currently in the session, updating within a
short time of them connecting/disconnecting. If we implemented, test that if user closes
browser, after a timeout they show offline. (We might or might not implement presence).
No duplication or ordering issues: Each message appears exactly once for each client, in
correct order. If using pub/sub, ensure no double send or missing messages.
Performance: The WS server can handle multiple connections and messages fluidly. The
overhead for each message (writing to DB, broadcasting) is fine for our expected user counts
(small groups).
Estimated Effort: 1–2 weeks. (A lot of pieces here, but many are straightforward if using existing
frameworks; the hardest is ensuring robust WS and turn logic).
Dependencies: This ties together many earlier parts: It needs campaigns and membership (to know
who to broadcast to, who can send), it needs auth (for identifying users), it uses orchestrator/agents
(for AI responses in chat), and uses possibly the dice engine (for showing roll results in chat). It also
needs an email capability configured. So it’s somewhat the capstone that integrates prior features.
Best done after those are in place.
Risks: WebSocket concurrency issues or crashes (we should handle if a broadcast fails or if Redis
pubsub misconfig). Also making sure that if server restarts, clients handle reconnect (maybe out-ofscope; minor annoyance if lost connection just refresh). Turn system may not fit all scenarios (some
games might not need strict turns except combat). But since we advertise asynchronous, turn
structure helps avoid confusion. Risk that players find it restrictive. Perhaps allow GM to toggle it.
MVP: have it always on or maybe only trigger it during "encounter mode" – but implementing modes
is heavy. Possibly always on but if not needed, players just end turn quickly. Notification emails risk:
spam or deliverability. Use proper email headers, include unsubscribe (maybe not needed for
transactional emails like turns). Also risk if emails accumulate (we should avoid sending multiple turn
emails if one already sent and player hasn’t acted – maybe only send once per turn). Could
implement a flag “notification_sent” for a turn so we don’t spam daily. Also ensure we don’t email on
every chat message – we won’t, only key events. There is a user privacy angle for email content – we
likely just say "Your turn in game X" rather than including game content, to be safe. Another risk:
ordering of events via WS: ensure that if a turn change triggers an email, the email logic doesn’t
block or delay WS message. Use background tasks for email. This package ties up loose ends, so risk
that something was missed (like cleaning up on campaign end, or scaling WS beyond one server –
which we plan to handle via Redis). At MVP, one server likely. Testing as a whole can be tricky if we try
to simulate real multi-user flows, but we’ll do what we can.
◦
◦
◦
◦
◦
◦
47.
48.
49.
42
Image Generation & Illustration (AI Image Agent)
Scope: Integrate the AI image generation capability via the Image agent. Allow players or GM to
request scene or character illustrations. Use an external service (or stub/local for MVP) to generate
images, store and display them in the session. This adds an immersive visual element to the
gameplay.
Deliverables:
Backend:
Finalize the image agent: implement the provider integration. Possibly use Replicate or
Stability API. For MVP (Phase 2 timeframe), we could use an external stable diffusion endpoint
(if cost permits) or simulate it by retrieving random relevant images from a library (as
placeholder). But ideally, at least one real integration to show actual AI generation.
The image agent function would accept a prompt and style, and then either synchronously
call the API or, better, enqueue a background job (Celery) to do it. It returns immediately with
some placeholder or acknowledgement, and the actual image result will be processed later.
We need a model for generated images; could reuse Document model (store them as flavor
docs with a tag "generated" or new type "image"). Or have a separate table but unnecessary.
Likely treat them as flavor docs (since players can see them, and they aren’t hidden usually).
When an image is ready, the worker should save the image file (e.g., as PNG in campaign’s
folder) and create a Document entry for it. Then notify via WebSocket (maybe send a message
of type "image" with reference to the file or an event telling clients to fetch it). Or simpler: just
insert a system message like "An image has been added: [filename]" and clients seeing that
will display it. But more elegant: have a message type that includes an image URL/ID so UI
can show the image inline.
Ensure to handle errors: if generation fails or times out, respond with a message like "Image
generation failed."
Multi-style support: define a few style presets (like "Realistic", "Cartoon", "Sketch"). The agent
might adjust the prompt or call different models accordingly. Could accept a style param and
append style-specific keywords to the prompt or choose a different model ID.
Rate limiting or cost control: maybe disallow too many image requests per hour or restrict to
GM only by default. We might not fully enforce for MVP but mention as caution.
Possibly caching: if a prompt was already generated in this campaign, reuse the existing
image to save cost/time. (We can hash prompt+style and check a cache dict or DB index).
Implement if easy.
Frontend:
Provide UI to request an image: e.g., a button "Generate Image" that opens a form where the
user (GM or player) enters a description (prompt) and selects a style from dropdown. On
submit, call an endpoint ( POST /images/generate or we reuse the documents upload for
images? Perhaps better a separate endpoint that triggers generation).
Immediately give user feedback: maybe show a loading spinner or placeholder in chat
"Generating image...". When the image is ready, replace that placeholder with the actual
image.
Display of generated images: When an image message/event comes in, display the image in
the chat feed or a separate gallery. Possibly as a thumbnail that can be clicked to enlarge. We
need to ensure the image is served via our documents system (so either embed via an <img
src="/documents/{id}"> or data URL).
50.
51.
52.
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
43
Style the image thumbnail (maybe a border or icon indicating style). Also possibly caption it
with the prompt text or who requested it.
If image generation takes time, we might also notify the requesting user if they leave the
session (maybe an email "Your image is ready" – probably not needed if it's within seconds).
Consider mobile data: perhaps do not auto-download huge images on mobile unless clicked –
but might skip such optimization now.
Tests:
If using actual API, testing is tricky (would not call real API in tests). We likely stub the image
agent in tests to immediately return a dummy image path. So test that calling the generation
endpoint yields a message or doc entry, and that eventually an image doc is created. We can
simulate the worker by directly calling the function instead of Celery for test.
Test that image docs created by agent are properly visible to all players (i.e., they probably
default to flavor type).
Test UI manually likely, but automated integration test could simulate an image request if we
stub generation, then ensure the client receives an event. Possibly difficult to do fully
automated, but maybe confirm the Document count increased and a message was broadcast.
Acceptance Criteria:
Users can successfully request AI-generated images during a session to depict scenes or
characters. For example, the GM can click "Generate Image", input "A misty forest at night
with glowing eyes in the dark", choose style "Sketch", and after some moments, an image
appears in the chat or images panel illustrating that prompt in a sketchy style.
The generated images are persisted and viewable by anyone in the campaign. If a player joins
later, they can see the images (likely via documents listing or as they scroll chat).
The image quality is as expected for the chosen style (this depends on model, but at least it
should make sense relative to prompt). If using a known stable diffusion model, we expect
decent results, though possibly not perfect. As long as it's not random noise and loosely
matches description.
The system handles the generation asynchronously without blocking other gameplay. The
chat/narration can continue while an image is being made. When ready, the image just pops
in.
Errors in generation (like content disallowed or service down) are handled gracefully: user
gets a message "Image could not be generated, please try a different description." and no
one is stuck waiting infinitely.
The cost of generation is somewhat controlled: e.g., if a user tries to spam the button, after a
few attempts maybe either queue them or show a message "Please wait for current image to
finish." We likely implement disabling the button while one is in progress or similar.
The images are stored in the campaign’s documents folder and can be downloaded if needed.
Possibly we treat them as flavor docs, so they show up in the documents list with tag "Image".
This way they don’t clutter if too many. But up to design.
Only authorized users can request images: maybe restrict to campaign members. If a random
user somehow got the endpoint and tries to generate in a campaign they’re not in, it should
fail.
The style options work distinctly: e.g., "8-bit" style yields a pixelated result, "Realistic" yields a
more photo-like one. (We can test by using different model IDs or prompt modifiers).
The entire flow (from request to image display) should typically complete within a reasonable
time (perhaps 5-30 seconds depending on model). We should set expectations in UI (like
show a loading status). If it takes too long or fails, we handle that.
◦
◦
◦
◦
◦
◦
◦
53.
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
44
Estimated Effort: 1–2 weeks (depending on integration complexity and debugging the external
calls).
Dependencies: Background task system (Celery) must be set up (from Agents package). Also
depends on documents/files (to save the image). Integration with orchestrator might be minimal
(the orchestrator might call image agent on its own for some scene, but likely we leave image
generation user-initiated for MVP). Possibly depends on an API key or account setup for image
service – which is more an external dependency.
Risks: The largest risk is cost and reliability of external AI service. If using a paid API, we need to
monitor usage to not exceed budgets. If using an open-source model locally, risk is complexity to set
up or performance. For MVP, probably use a cloud API with limited free or cheap usage (OpenAI’s
DALL-E or Stability’s trial).
Also risk: content safety – stable diffusion could produce unexpected or inappropriate images for
some prompts. We should ideally use a model with a safety filter or do our own check (some have
NSFW filters built in). We could use prompt engineering to try to avoid explicit content. For now,
assume best or include a content warning in terms.
Another risk is technical: handling binary data streams and saving images – ensure file not corrupted
and properly closed. Also ensure not leaving huge temp files if user generates many images.
Possibly implement a limit (maybe the first model returns 512x512 images which are a few hundred
KB, manageable).
Also user experience risk: if images are too slow or poor quality, users might be disappointed.
Manage by setting expectations (maybe label as experimental).
Testing risk: Hard to auto-test because it’s not deterministic. But we can test our pipeline with a
dummy generator function.
Integration with story: not mandatory, but possibly risk that players may misuse image gen for offtopic stuff. Not a big issue in closed group. If more public, might moderate prompt (like disallow hate
content in prompts). Possibly out-of-scope now.
PDF Import & Automated Parsing Improvements
Scope: Improve the PDF character sheet import functionality, making it more robust across different
sheet layouts and possibly using ML-based extraction for better accuracy. Also consider extending
parsing to other text-based content (like importing quest PDFs into hidden docs or similar, if
beneficial). Essentially, refine what was done in the Character Service import with additional
techniques or training.
Deliverables:
Refined parsing code in server/tools/pdf_import.py : incorporate additional heuristics
or patterns as we gather more sample sheets. Perhaps handle multiple columns or different
ordering of fields. Possibly allow the user to select which game system the PDF is (if we
support multiple) to apply correct parsing logic.
Consider using an OCR for scanned sheets: integrate pytesseract or a similar library to
get text from image-based PDFs, then parse that text. This would allow imports of scanned
documents at basic level, though error-prone.
If we find an open-source model (like a layoutlm or a fine-tuned model for extracting RPG
character info), evaluate integrating it. (This might be heavy, and likely we stick to heuristics
due to time).
Possibly allow user adjustments via a mapping UI: e.g., after uploading PDF and initial parse,
present an interface where the text that was extracted is shown alongside fields, and user can
54.
55.
56.
57.
58.
59.
◦
◦
◦
◦
45
correct any mis-placed values before saving. For MVP extension, maybe not a fancy UI, but
even a simple text area to edit JSON or fields. But a guided UI would be better: highlight
extracted name vs what user sees, etc. Could be too much to implement comprehensively –
maybe postpone detailed UI improvements.
Logging or storing of import errors: maybe create a log of fields we failed to parse for
analytics (not crucial for user, but for developer to improve parser). Or allow user to send
feedback easily if an import fails.
Extend import beyond characters: We might provide a similar parsing for other content like
NPC stat blocks from PDFs, or maybe parse a whole adventure module into notes. That’s
ambitious; possibly skip unless easy structures.
Tests: use more sample PDF texts to ensure our parser improvements handle them. If
possible, get a couple of different character sheet PDF outputs (maybe one from D&D Beyond
PDF export, one form-fillable PDF, one scanned example if feasible). Ensure our extraction
function populates fields correctly for each.
Acceptance Criteria:
The PDF import success rate is higher: for example, with the official D&D 5e sheet, the
importer now captures not only ability scores but also secondary stats like proficiency bonus,
initiative, maybe even attack values if present, etc. Basically, more of the sheet is correctly
interpreted compared to MVP version.
The importer can handle slight layout differences (e.g., if a homebrew sheet has stats in a
different position, maybe we added support for that by adjusting patterns or letting user
specify an offset/template). We might not do arbitrary templates, but at least cover the
common cases we anticipate.
If the PDF is image-based (scanned), and if tesseract is integrated, the importer will at least
extract the text and try to parse it. The accuracy might drop, but it should get the main
numbers correct if the scan is clear. If it cannot, it should inform the user that the quality is
insufficient rather than creating a wrong character.
The user still has an opportunity to review and correct parsed data before finalizing the
import. For instance, after import, show them the values for each stat that will be saved,
which they can edit if something looks off (like DEX shows 14 but should be 16). This review
step ensures that even if parsing isn’t 100%, the user can fix things easily. Acceptance here is
that the UI for this is straightforward and not confusing.
The import is still secure: we handle PDFs safely (we use libraries that mitigate malicious PDF
exploits by not executing any embedded scripts, etc. PyMuPDF is generally safe for reading).
If a PDF is huge (like 100 pages), maybe we impose a reasonable page limit or only parse first
few pages if expecting a sheet.
Performance: Importing a PDF (especially with OCR) can be slow (a couple of seconds to tens
of seconds). We should not block the main server thread for long. Possibly run the import in a
background task or thread if heavy. Acceptance: importing a sheet might take, say, up to 5-10
seconds, and the user gets feedback (spinner) and the server doesn’t hang for others. If we
integrate with Celery, maybe do it asynchronously with a progress bar or just async result.
Possibly not needed if times are short and we can just wait.
We maintain or improve legal compliance: ensure any parsed data used is within what’s
allowed (should be, as it’s user’s own data). We’re not storing or distributing any copyrighted
text beyond for that user’s use.
Estimated Effort: 1–3 weeks (depending on the complexity of improvements and testing with actual
documents).
◦
◦
◦
60.
◦
◦
◦
◦
◦
◦
◦
61.
46
Dependencies: Character Service (initial import functionality) must be in place. Possibly need an
OCR tool installed if we do that (pytesseract requires Tesseract OCR installed on system; could be a
hassle to set up in environment or container). Alternatively, use an online OCR API (but that adds
cost and dependency). Might skip scanned docs if environment setup is too much.
Risks: Diminishing returns – we could spend a lot of time trying to perfectly parse any sheet and still
fail on edge cases. We should aim for “good enough” for common formats and not stress beyond
that. Also risk of over-engineering the UI for corrections – need to decide a reasonable approach to
let user fix things without building a full drag-and-drop mapping UI (which would be cool but timeconsuming). Perhaps a simple form with fields prefilled from parse is enough.
Integrating OCR is also risky as it might mis-recognize numbers (e.g., 5 vs 3) which could lead to
subtle errors. We might label OCR support as experimental if added.
Another risk: by Phase 2, maybe D&D Beyond opens an API or better data access, which could make
PDF parsing less needed for those users. But we can’t assume that. Our code should be ready to
adapt if an official API can be used (which would be easier – we could fetch structured JSON directly if
allowed).
Testing improvements might be limited by available sample PDFs – we should gather some. Possibly
ask any testers to send sample sheets to refine. If none, internet might have some (just ensure not
to include real personal info).
There is also risk in the time it takes vs value – if time is short, we might deprioritize some
improvements. The acceptance should be adjusted to what we manage (e.g., maybe we parse two
known formats near perfectly, which is still a win).
Testing, CI & Deployment Pipeline
Scope: Establish a robust CI/CD pipeline and ensure all aspects of the system are well-tested
and the deployment process is smooth. This includes writing tests for any remaining untested
parts, setting up CI workflows (if not already fully done), and preparing deployment
configurations (Docker, etc.) for production.
Deliverables:
Complete test coverage: Review test cases and add any missing tests for critical flows or edge
cases. This might include testing multi-agent orchestration sequence, error handling paths,
security tests (like ensuring certain forbidden actions truly result in 403), performance tests
(maybe a simple load test script to simulate many messages or concurrent users), etc.
Possibly use mocking to test scenarios like AI API down (simulate exceptions and ensure our
code handles them gracefully).
Continuous Integration workflows:
If not done, finalize GitHub Actions workflows for Python backend tests, JS frontend
tests, E2E tests, linting, etc. Ensure they run reliably (tweak any flakiness). Possibly
configure parallel jobs to cut down run time if long.
Include build artifacts like coverage reports or test reports for transparency. If
possible, set up slack/email notifications on CI failures for the team.
Deployment:
Create a Dockerfile for the backend (maybe multi-stage: one to install deps and one
to run uvicorn/gunicorn).
Create a Dockerfile for the frontend (to build static files and serve them, or could
serve via backend static but likely easier separate via something like Nginx or use the
62.
63.
64.
◦
◦
◦
◦
▪
▪
◦
▪
▪
47
same uvicorn to serve static). Might combine in one image for simplicity (serve static
from FastAPI or use starlette static files).
Compose or Helm: at least a docker-compose file for running the whole stack (web,
worker, db, redis). Use environment variables for config (like DB URL, API keys).
Document how to deploy (maybe in README). Possibly set up a staging environment
on some free cloud or local VM to test it works outside dev environment.
If possible, set up automation so that pushing a new version triggers building the
images and maybe deploying to a server. For instance, use GitHub Actions to build and
push a Docker image to a registry on new release tag.
Developer ergonomics:
Create test fixtures or a script to easily populate test data (like a fabfile or just reusing
playthrough.py ).
Possibly include a VSCode devcontainer or environment config for easy setup. Not
mandatory but could be nice.
Pre-commit hook configuration (so contributors auto-run formatting/tests before
commit).
Clean up repository: ensure all docs (README, PROJECT_PLAN if included, etc.) are updated to
reflect current state. Perhaps add usage examples or screenshots for clarity.
Acceptance Criteria:
The test suite covers the vast majority of the code. We should aim for a high percentage (e.g.
>85% coverage) and, more importantly, all critical logic paths (auth, permissions, agent flows,
etc.) have tests. If a new change is made, failing tests will catch regressions reliably.
CI passes consistently. Intermittent flakiness should be eliminated or minimized. If some E2E
tests are flaky due to timing, add waits or retries to stabilize. The CI results on the repo give
confidence that a green build is deployable.
The pipeline is efficient: ideally, CI completes in a reasonable time (e.g., under 10 minutes
total). If it’s slower, maybe parallelize or optimize.
Deployability: We can bring up the entire application with one command (e.g., dockercompose up ) on a new machine and it works – serving the frontend, connecting to backend,
all features functioning. This verifies that our config is environment-agnostic (no hardcoded
paths or keys).
The Docker images we produce are not too large (maybe base on slim images, and multistage to avoid dev dependencies in final image). Also ensure production config (like using
gunicorn for serving, and proper static file serving).
We have environment variables for secrets (e.g., OPENAI_API_KEY, EMAIL_SMTP_SERVER, etc.)
and none of those are left in code or repository. The app should read from env or config files.
The deployment documentation clearly states what env vars need to be set and any setup
steps (like running db migrations).
If we use Kubernetes later, maybe provide a basic manifest or Helm chart (not strictly needed
for MVP unless aiming to deploy on K8s).
Logging and monitoring: ensure that in production mode, logs are appropriately leveled (info
for normal ops, debug only when enabled). Possibly integrate a simple health-check endpoint
(like GET /health returns OK) for container orchestration to know it’s up.
Developer documentation: A new developer should be able to read our README or
contributing guide and run the app, run tests (maybe make test ), and understand how to
build upon it. Also, mention the use of AI in development if we want others to continue that
approach.
▪
▪
▪
◦
▪
▪
▪
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
◦
48
All high-priority issues found during previous testing phases are resolved. If any bug was
logged, tests should be added to ensure it doesn’t recur.
If applicable, an initial version is deployed to an environment (maybe an AWS EC2 or Heroku
container) and tested as a whole. This is more a final verification that in a production-like
setting things work (no missing static, no CORS issues, etc.).
Estimated Effort: 1–2 weeks (some of these tasks may be ongoing throughout, but finalizing
them and fixing any last issues fits here).
Dependencies: None specifically, it’s an overarching task. But it wraps up after core
functionality is done, so that we can test everything.
Risks: Not many risks, mostly just time and thoroughness. Ensuring we catch everything.
Possibly some tests might be hard to automate (like testing actual email sending or external
API calls). We might use test doubles or just test our handling and skip actual network calls.
Also, making sure our Docker configuration matches development (e.g., manage static files
properly, set correct UVICORN workers, etc.). If not careful, the deployed app could behave
differently. We mitigate by doing at least one test deploy. Another risk: environment
differences (e.g., file paths or OS differences in e.g., path handling, line endings, etc.). Using
containers helps unify environment. The team should also consider maintenance: maybe set
up dependabot for dependencies, or at least pin versions so that new updates don’t break
things unexpectedly post-release. Possibly beyond immediate scope, but part of
maintainability.
CI false positives/negatives: occasionally tests might not cover a scenario which fails in
production because environment is slightly different. Hard to predict, but thorough
integration tests reduce that risk. After this stage, theoretically, the product is ready for a
broader release or at least a beta test. So the risk is missing something that real users
encounter; we plan to address that quickly if so (with patches, which our CI/CD should allow
to roll out easily).
With these detailed packages and improvements, we ensure TavernTAIls is feature-complete for its MVP and
early phases, tested, and deployable. Each work package has clear deliverables and acceptance criteria
which have been integrated and refined in this unified plan, guiding both human and AI contributors in
implementation.
Conclusion: By merging the high-level project plan with the breakdown of work packages, we have a
unified and enhanced roadmap for TavernTAIls. This document outlines everything from the vision and
architecture down to specific tasks and criteria for success, addressing potential gaps in logic, security,
integration, scalability, and user experience along the way. It also includes recommendations for using AI in
development, cost-effective infrastructure choices, and steps to ensure the platform is robust and
maintainable. With this plan, the development team (human and AI assistants together) can proceed with
clarity and confidence toward delivering TavernTAIls as an AI-assisted tabletop RPG platform ready for both
solo adventurers and collaborative storytellers.
PROJECT_PLAN.md
https://github.com/DegeneratesAnonymous/TavernTails/blob/c8fa0ab20cb3e636a7a30938d036b170c1cc54c7/PROJECT_PLAN.md
◦
◦
◦
◦
◦
22 11
1 2 3 4 5 6 7 9 11 12 13 14 16 17 18 19 21 22
49
PROJECT_PLAN_BREAKDOWN.md
https://github.com/DegeneratesAnonymous/TavernTails/blob/c8fa0ab20cb3e636a7a30938d036b170c1cc54c7/
PROJECT_PLAN_BREAKDOWN.md
8 10 15 20
50