# Beyond 20

> Screenshot auto-updated on every merge to `main` via the
> [screenshot-update](https://github.com/DegeneratesAnonymous/TavernTails/actions/workflows/screenshot-update.yml) workflow.

![Beyond 20](https://raw.githubusercontent.com/DegeneratesAnonymous/TavernTails/main/docs/screenshots/15-beyond20.png)

The Beyond 20 integration settings page — accessible from the
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
  before rolling on D&D Beyond.

---

_← Back to [[Home]]_
