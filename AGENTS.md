# Agent Modules Documentation

This file documents the agent-based architecture for the TavernTAIls AI GM web app. Each agent is responsible for a distinct aspect of gameplay or management.

## Agents Overview

### 1. Narrative Agent
- **Role:** Drives gameplay, generates scene narration, prompts players, manages turn order.
- **Location:** `server/agents/narrative.py`, `client/src/agents/NarrativeAgent.tsx`

### 2. Scene Analysis Agent
- **Role:** Detects needed dice rolls, enforces rules, prompts for player actions.
- **Location:** `server/agents/scene.py`, `client/src/agents/SceneAgent.tsx`

### 3. NPC/Enemy Manager Agent
- **Role:** Profiles NPCs/enemies, tracks stats, motivations, and initiative; manages combat.
- **Location:** `server/agents/npc.py`, `client/src/agents/NPCAgent.tsx`

### 4. Storyboard Agent
- **Role:** Tracks campaign progress, scenes, branching paths, and unresolved threads.
- **Location:** `server/agents/storyboard.py`, `client/src/agents/StoryboardAgent.tsx`

### 5. Notes Agent
- **Role:** Logs session notes, recaps, and provides !notes on request.
- **Location:** `server/agents/notes.py`, `client/src/agents/NotesAgent.tsx`

### 6. Image Generation Agent
- **Role:** Creates scene images using AI for immersion.
- **Location:** `server/agents/image.py`, `client/src/agents/ImageAgent.tsx`

## Development Order
1. Narrative Agent
2. Scene Analysis Agent
3. NPC/Enemy Manager Agent
4. Storyboard Agent
5. Notes Agent
6. Image Generation Agent

## Integration Plan
- Each agent has a backend (FastAPI) module and a frontend (React) component.
- Agents communicate via REST API endpoints.
- Documentation and code comments will be updated as agents are expanded.

---
For questions or handoff, refer to this file and the README.md for project context.
