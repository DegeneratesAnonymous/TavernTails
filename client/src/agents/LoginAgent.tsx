// LoginAgent: Handles player login and session restoration
import React, { useState } from 'react';
import { buildApiUrl } from '../api';

const LoginAgent: React.FC = () => {
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [profile, setProfile] = useState<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function formatDetail(detail: any) {
    if (Array.isArray(detail)) {
      return detail
        .map((d: any) => {
          const loc = Array.isArray(d.loc) ? d.loc.join('.') : d.loc;
          return `${loc}: ${d.msg}`;
        })
        .join('; ');
    }
    if (detail && typeof detail === 'object') {
      if (detail.msg) return detail.msg;
      return JSON.stringify(detail);
    }
    return String(detail ?? '');
  }

  const handleLogin = async () => {
    setError('');
    setLoading(true);
    try {
      const res = await fetch(buildApiUrl('/player/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      setLoading(false);
      if (res.ok) {
        const body = await res.json();
        // store access token for authenticated API calls
        if (body && body.access_token) {
          try { localStorage.setItem('access_token', body.access_token) } catch(_) {}
        }
        setProfile(body.profile || body);
      } else {
        try {
          const err = await res.json();
          const detail = err.detail || err || '';
          setError(formatDetail(detail) || 'Invalid credentials or user not found.');
        } catch (_) {
          setError('Invalid credentials or user not found.');
        }
      }
    } catch (e) {
      setLoading(false);
      setError('Network error. Is the backend running?');
    }
  };

  return (
    <div>
      <h2>Login</h2>
      <div>
        <label className="sr-only" htmlFor="la-email">Email</label>
        <input id="la-email" className="input" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" />
      </div>
      <div>
        <label className="sr-only" htmlFor="la-pass">Password</label>
        <input id="la-pass" className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" />
      </div>
      <button className="btn" onClick={handleLogin} disabled={loading} aria-disabled={loading}>{loading ? 'Logging in...' : 'Login'}</button>
      {error && <div className="error" role="alert">{error}</div>}
      {profile && (
        <pre>{JSON.stringify(profile, null, 2)}</pre>
      )}
    </div>
  );
};

export default LoginAgent;
