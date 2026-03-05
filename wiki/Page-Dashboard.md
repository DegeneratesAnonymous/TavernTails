# Dashboard

> Screenshot auto-updated on every merge to `main` via the
> [screenshot-update](https://github.com/DegeneratesAnonymous/TavernTails/actions/workflows/screenshot-update.yml) workflow.

![Dashboard](https://raw.githubusercontent.com/DegeneratesAnonymous/TavernTails/main/docs/screenshots/04-dashboard.png)

The authenticated home screen — shown immediately after a successful login.

## Layout

The Dashboard uses a shell layout with three persistent UI regions:

| Region | Contents |
|---|---|
| **Top bar** | TavernTAIls brand, notification bell (🔔), account button (👤) |
| **Slide-out drawer** | Navigation links to all major views; triggered by the ☰ hamburger icon |
| **Main content area** | Changes based on the selected view |

## Dashboard Home Content

When the `home` view is active, the main area greets the user by display name
("Welcome, ${name}") and presents six quick-action tiles:

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

The 👤 icon navigates directly to the [[Account Settings|Page-Account]] view.

---

_← Back to [[Home]]_
