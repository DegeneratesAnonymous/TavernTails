import React, { useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../api';

type Props = {
  identifier: string | null
}

const Beyond20Agent: React.FC<Props> = ({ identifier }) => {
  const [domainsText, setDomainsText] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [invalidLines, setInvalidLines] = useState<string[]>([]);

  const resolvedIdentifier = useMemo(() => (identifier ? String(identifier).trim() : ''), [identifier])

  useEffect(() => {
    if (!resolvedIdentifier) return;
    const fetchDomains = async () => {
      try {
        const res = await apiFetch(`/player/beyond20?identifier=${encodeURIComponent(resolvedIdentifier)}`)
        if (res.ok) {
          const data = await res.json();
          if (data.domains) setDomainsText(data.domains.join('\n'));
        }
      } catch (e) {
        // ignore
      }
    };
    fetchDomains();
  }, [resolvedIdentifier]);

  const validateDomains = (text: string) => {
    const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const invalid: string[] = [];
    for (const ln of lines) {
      if (!/^https?:\/\//i.test(ln) || /\s/.test(ln)) {
        invalid.push(ln);
      }
    }
    setInvalidLines(invalid);
    return invalid.length === 0;
  };

  const handleSave = async () => {
    if (!resolvedIdentifier) {
      setMessage('Sign in to save custom domains.');
      return;
    }
    setLoading(true);
    setMessage('');
    // client-side validation
    const ok = validateDomains(domainsText);
    if (!ok) {
      setMessage('Some domain lines are invalid. Fix them before saving.');
      setLoading(false);
      return;
    }
    try {
      const payload = { identifier: resolvedIdentifier, domains_text: domainsText };
      const res = await apiFetch('/player/beyond20', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok) {
        setMessage('Saved.');
        setDomainsText((data.domains || []).join('\n'));
      } else {
        setMessage(data.detail || 'Failed to save');
      }
    } catch (e) {
      setMessage('Network error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="muted" style={{ fontSize: 13 }}>
        Enter one domain per line. Include the protocol (http:// or https://). Wildcards (*) are allowed for subdomains and paths.
      </div>
      {!resolvedIdentifier ? (
        <div className="inline-alert">
          Sign in to manage custom domains. Once signed in, your account identifier will be used automatically.
        </div>
      ) : (
        <div className="muted" style={{ fontSize: 12 }}>
          Using account: <span className="code-block" style={{ padding: '2px 6px' }}>{resolvedIdentifier}</span>
        </div>
      )}

      <div className="stack" style={{ gap: 6 }}>
        <label className="muted">Custom domains (one per line)</label>
        <textarea
          className="input input-mono"
          value={domainsText}
          onChange={(e) => {
            setDomainsText(e.target.value)
            validateDomains(e.target.value)
          }}
          rows={8}
          disabled={!resolvedIdentifier}
        />
      </div>

      {invalidLines.length > 0 && (
        <div className="inline-alert inline-alert-error">
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Invalid lines</div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {invalidLines.map((line) => (
              <li key={line}><span className="code-block" style={{ padding: '2px 6px' }}>{line}</span></li>
            ))}
          </ul>
        </div>
      )}

      <div className="row-wrap" style={{ alignItems: 'center' }}>
        <button className="btn btn-secondary" onClick={handleSave} disabled={loading || !resolvedIdentifier}>
          {loading ? 'Saving…' : 'Save domains'}
        </button>
        {message ? <span className="muted">{message}</span> : null}
      </div>
    </div>
  );
};

export default Beyond20Agent;
