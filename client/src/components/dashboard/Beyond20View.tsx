import React from 'react'

import Beyond20Agent from '../../agents/Beyond20Agent'
import PageHeader from '../ui/PageHeader'

type Props = {
  activeSessionId: string | null
  identifier?: string | null
}

export default function Beyond20View({ identifier }: Props) {
  return (
    <section className="stack-lg">
      <div className="card card-pad stack">
        <PageHeader
          title="Beyond 20"
          subtitle="Connect the Beyond 20 browser extension to relay rolls into your TavernTails session chat."
        />
        <p className="muted" style={{ marginTop: 0 }}>
          Beyond 20 is a free browser extension. Once installed, it automatically detects rolls on your D&amp;D Beyond character sheet and forwards them into your active TavernTails session. No additional software or installs are required beyond the extension itself.
        </p>

        <div className="row-wrap" style={{ gap: 8 }}>
          <a
            className="btn btn-secondary"
            href="https://chrome.google.com/webstore/detail/beyond-20/gnblbpbepfbfmoobegdogkglpbhcjofh"
            target="_blank"
            rel="noopener noreferrer"
          >
            Install for Chrome
          </a>
          <a
            className="btn btn-secondary"
            href="https://addons.mozilla.org/en-US/firefox/addon/beyond-20/"
            target="_blank"
            rel="noopener noreferrer"
          >
            Install for Firefox
          </a>
        </div>
      </div>

      <div className="card card-pad stack">
        <h3 className="section-title">Beyond 20 Custom Domains</h3>
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          If TavernTails is hosted on a custom domain, add it here so Beyond 20 knows to send rolls to this site.
        </p>
        <Beyond20Agent identifier={identifier ?? null} />
      </div>
    </section>
  )
}
