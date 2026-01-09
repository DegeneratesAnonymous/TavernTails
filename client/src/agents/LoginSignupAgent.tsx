import React, { useState } from 'react';
import '../LoginSignupNew.css';
import '../LoggedIn.css';
import HamsterWheel from '../components/HamsterWheel';
import LoggedInDashboard from '../components/LoggedInDashboard';
import { buildApiUrl } from '../api';

const LoginSignupAgent: React.FC = () => {
  const [isSignup, setIsSignup] = useState(false);
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [signupName, setSignupName] = useState('');
  const [signupEmail, setSignupEmail] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [signupAge, setSignupAge] = useState('');
  const [error, setError] = useState('');
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [verificationToken, setVerificationToken] = useState('');
  const [unverifiedEmail, setUnverifiedEmail] = useState('');
  const devCredentials = { email: 'test@example.com', password: 'secret' };

  React.useEffect(() => {
    if (profile) {
      document.body.classList.add('logged-in');
    } else {
      document.body.classList.remove('logged-in');
    }
    return () => {
      document.body.classList.remove('logged-in');
    };
  }, [profile]);

  React.useEffect(() => {
    if (profile) return;
    const token = localStorage.getItem('access_token');
    if (!token) return;
    let canceled = false;
    const headers: any = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
    fetch(buildApiUrl('/player/me'), { headers })
      .then((res) => {
        if (!res.ok) {
          return Promise.reject('Unable to refresh profile');
        }
        return res.json();
      })
      .then((data) => {
        if (canceled) return;
        if (data?.profile) setProfile(data.profile);
      })
      .catch(() => {
        if (canceled) return;
        localStorage.removeItem('access_token');
      });
    return () => {
      canceled = true;
    };
  }, [profile]);

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

  const applyAuthResponse = (data: any, options?: { preserveVerification?: boolean }) => {
    if (!data) return;
    if (data.access_token) {
      localStorage.setItem('access_token', data.access_token);
    }
    const resolvedProfile = data.profile || data
    const email = resolvedProfile?.email
    const username = resolvedProfile?.username
    if (email) localStorage.setItem('user_email', String(email))
    if (username) localStorage.setItem('user_username', String(username))
    setProfile(resolvedProfile);
    setError('');
    if (!options?.preserveVerification) {
      setUnverifiedEmail('');
      setVerificationToken('');
    }
  };

  const performAuthRequest = async (path: string, payload: Record<string, any>) => {
    try {
      const res = await fetch(buildApiUrl(path), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const parsed = await res.json().catch(() => null);
      if (res.ok) {
        return { data: parsed ?? {} };
      }
      const errorDetail = parsed?.detail ?? parsed ?? res.statusText ?? 'Request failed';
      return { errorDetail };
    } catch (err: any) {
      return { errorDetail: err?.message || 'Network error occurred' };
    }
  };

  const normalizeLoginIdentifier = (value: string) => {
    const trimmed = value.trim();
    const looksLikeEmail = trimmed.includes('@');
    return {
      raw: trimmed,
      email: looksLikeEmail ? trimmed.toLowerCase() : undefined,
      name: looksLikeEmail ? trimmed : trimmed || undefined
    };
  };

  const handleLogin = async (overrides?: { email?: string; password?: string }) => {
    const rawEmailInput = overrides?.email ?? loginEmail;
    const rawPasswordInput = overrides?.password ?? loginPassword;
    const identifierInfo = normalizeLoginIdentifier(rawEmailInput || '');
    const passwordValue = rawPasswordInput.trim();
    setLoginEmail(identifierInfo.raw);
    setLoginPassword(passwordValue);
    if (!identifierInfo.raw || !passwordValue) {
      setError('Enter both email and password.');
      return;
    }
    setError('');
    setLoading(true);
    const payload: Record<string, any> = { password: passwordValue };
    if (identifierInfo.email) {
      payload.email = identifierInfo.email;
      payload.name = identifierInfo.raw;
    } else {
      payload.name = identifierInfo.raw;
    }
    const { data, errorDetail } = await performAuthRequest('/player/login', payload);
    setLoading(false);
    if (errorDetail) {
      const detailStr = formatDetail(errorDetail);
      if (detailStr === 'Email not verified') {
        setUnverifiedEmail(identifierInfo.raw);
        setError('Email not verified - please enter the verification token sent to your email.');
      } else {
        setError(detailStr || 'Invalid credentials or user not found.');
      }
      return;
    }
    applyAuthResponse(data);
  };

  const handleDevLogin = () => handleLogin(devCredentials);
  const handleSignup = async () => {
    setError('');
    setLoading(true);
    const cleanEmail = signupEmail.trim().toLowerCase();
    const cleanName = signupName.trim();
    const cleanPassword = signupPassword.trim();
    setSignupEmail(cleanEmail);
    setSignupName(cleanName);
    setSignupPassword(cleanPassword);
    if (!cleanEmail || !cleanPassword) {
      setLoading(false);
      setError('Email and password are required.');
      return;
    }
    const payload = { email: cleanEmail, password: cleanPassword, name: cleanName || undefined, age: signupAge ? Number(signupAge) : undefined };
    const { data, errorDetail } = await performAuthRequest('/player/signup', payload);
    setLoading(false);
    if (errorDetail) {
      setError(formatDetail(errorDetail) || 'Signup failed.');
      return;
    }
    setIsSignup(false);
    setUnverifiedEmail(signupEmail);
    setVerificationToken(data?.verification_token || '');
    setError('Account created - verify your email before logging in (token included for dev).');
  };

  const handleVerify = async () => {
    if (!unverifiedEmail || !verificationToken) return;
    setLoading(true);
    try {
      const res = await fetch(buildApiUrl('/player/verify-email'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: unverifiedEmail, token: verificationToken })
      });
      setLoading(false);
      if (res.ok) {
        setError('Email verified - you can now log in.');
        setUnverifiedEmail('');
        setVerificationToken('');
      } else {
        const err = await res.json();
        const detail = err.detail || err || '';
        const detailStr = formatDetail(detail);
        setError(detailStr || 'Verification failed');
      }
    } catch (e) {
      setLoading(false);
      setError('Network error during verification');
    }
  };

  const handleResendVerification = async () => {
    if (!unverifiedEmail) return;
    setLoading(true);
    try {
      const res = await fetch(buildApiUrl('/player/resend-verification'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: unverifiedEmail })
      });
      setLoading(false);
      if (res.ok) {
        const data = await res.json();
        setVerificationToken(data.verification_token || '');
        setError('Verification token resent (returned for dev).');
      } else {
        const err = await res.json();
        const detail = err.detail || err || '';
        const detailStr = formatDetail(detail);
        setError(detailStr || 'Failed to resend verification');
      }
    } catch (e) {
      setLoading(false);
      setError('Network error during resend');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_email')
    localStorage.removeItem('user_username')
    setProfile(null);
    setLoginEmail('');
    setLoginPassword('');
    setSignupName('');
    setSignupPassword('');
    setSignupEmail('');
    setSignupAge('');
    setIsSignup(false);
    setUnverifiedEmail('');
    setVerificationToken('');
  };

  return (
    <div style={{ minHeight: '100vh' }}>
      {loading && <HamsterWheel />}
      {!profile ? (
        <div className="container" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ width: '420px', maxWidth: '96%', padding: 20 }}>
            {!isSignup ? (
              <section>
                <h2 style={{ color: 'white', marginBottom: 12 }}>Login</h2>
                <form onSubmit={e => { e.preventDefault(); handleLogin(); }} aria-busy={loading} aria-live="polite">
                  <label className="sr-only" htmlFor="loginEmail">Email</label>
                  <input id="loginEmail" className="input" type="email" placeholder="Email" value={loginEmail} onChange={e => setLoginEmail(e.target.value)} autoComplete="email" />

                  <label className="sr-only" htmlFor="loginPassword">Password</label>
                  <input id="loginPassword" className="input" type="password" placeholder="Password" value={loginPassword} onChange={e => setLoginPassword(e.target.value)} autoComplete="current-password" />

                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button className="btn" type="submit" disabled={loading} aria-disabled={loading}>
                      {loading ? 'Logging in...' : 'Login'}
                    </button>
                    <button type="button" className="btn" onClick={() => setIsSignup(true)} style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.12)', color: 'white' }}>Sign up</button>
                  </div>
                  <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button type="button" className="btn" onClick={handleDevLogin} disabled={loading} style={{ background: 'rgba(255,255,255,0.08)', boxShadow: 'none', fontSize: 13, padding: '8px 14px' }}>
                      Use dev login
                    </button>
                    <span style={{ fontSize: 12, opacity: 0.75 }}>test@example.com / secret</span>
                  </div>

                  {error && <div className="error" role="alert">{error}</div>}
                  {unverifiedEmail && (
                    <div style={{ marginTop: 8 }}>
                      <label className="sr-only" htmlFor="verifyToken">Verification Token</label>
                      <input id="verifyToken" className="input" type="text" placeholder="Verification token" value={verificationToken} onChange={e => setVerificationToken(e.target.value)} />
                      <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                        <button className="btn" type="button" onClick={handleVerify}>Verify Email</button>
                        <button className="btn" type="button" onClick={handleResendVerification}>Resend</button>
                      </div>
                    </div>
                  )}
                </form>
              </section>
            ) : (
              <section>
                <h2 style={{ color: 'white', marginBottom: 12 }}>Sign Up</h2>
                <form onSubmit={e => { e.preventDefault(); handleSignup(); }}>
                  <input className="input" type="email" placeholder="Email" value={signupEmail} onChange={e => setSignupEmail(e.target.value)} />
                  <input className="input" type="text" placeholder="Display Name (optional)" value={signupName} onChange={e => setSignupName(e.target.value)} />
                  <input className="input" type="password" placeholder="Password" value={signupPassword} onChange={e => setSignupPassword(e.target.value)} />
                  <input className="input" type="number" placeholder="Your age (optional)" value={signupAge} onChange={e => setSignupAge(e.target.value)} />
                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button className="btn" type="submit">Sign Up</button>
                    <button type="button" className="btn" onClick={() => setIsSignup(false)} style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.12)', color: 'white' }}>Back to Login</button>
                  </div>
                  {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
                </form>
              </section>
            )}
          </div>
        </div>
      ) : (
        <LoggedInDashboard profile={profile} onLogout={handleLogout} />
      )}
    </div>
  );
};

export default LoginSignupAgent;
