import React, { useEffect, useState } from 'react';
import { buildApiUrl } from '../api';

const Beyond20Agent: React.FC = () => {
  const [name, setName] = useState('BilboBaggins');
  const [domainsText, setDomainsText] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [invalidLines, setInvalidLines] = useState<string[]>([]);

  useEffect(() => {
    if (!name) return;
    // fetch existing domains for this user
    const fetchDomains = async () => {
      try {
        const url = buildApiUrl(`/player/beyond20?name=${encodeURIComponent(name)}`);
        const res = await fetch(url, { method: 'GET' });
        if (res.ok) {
          const data = await res.json();
          if (data.domains) setDomainsText(data.domains.join('\n'));
        }
      } catch (e) {
        // ignore
      }
    };
    fetchDomains();
  }, [name]);

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
      const payload = { name, domains_text: domainsText };
      const res = await fetch(buildApiUrl('/player/beyond20'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
    <div style={{ maxWidth: 680, margin: '12px auto', color: 'var(--text)' }}>
      <h3>Beyond20 Custom Domains</h3>
      <p style={{ color: 'var(--muted-text)', marginTop: 0 }}>
        Enter one domain per line. Include the protocol (http:// or https://). Wildcards (*) are allowed for subdomains and paths.
      </p>
      <div style={{ marginBottom: 8 }}>
        <label style={{ display: 'block', marginBottom: 6 }}>Player name</label>
        <input value={name} onChange={e => setName(e.target.value)} style={{ width: '100%', padding: 8, borderRadius: 6, border: '1px solid rgba(255,255,255,0.06)', background: 'var(--surface)', color: 'var(--text)' }} />
      </div>
      <div>
        <label style={{ display: 'block', marginBottom: 6 }}>Custom domains (one per line)</label>
        <textarea value={domainsText} onChange={e => { setDomainsText(e.target.value); validateDomains(e.target.value); }} rows={8} style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid rgba(255,255,255,0.06)', background: 'var(--surface)', color: 'var(--text)', fontFamily: 'monospace' }} />
      </div>
      {invalidLines.length > 0 && (
        <div style={{ marginTop: 8, color: 'var(--error)' }}>
          <strong>Invalid lines:</strong>
          <ul>
            {invalidLines.map(l => <li key={l}><code style={{ color: 'var(--text)' }}>{l}</code></li>)}
          </ul>
        </div>
      )}
      <div style={{ marginTop: 10 }}>
        <button onClick={handleSave} disabled={loading} style={{ padding: '8px 14px', borderRadius: 6, background: 'var(--highlight)', color: 'black', border: 'none' }}>{loading ? 'Saving…' : 'Save'}</button>
        <span style={{ marginLeft: 12, color: 'var(--muted-text)' }}>{message}</span>
      </div>
    </div>
  );
};

export default Beyond20Agent;
