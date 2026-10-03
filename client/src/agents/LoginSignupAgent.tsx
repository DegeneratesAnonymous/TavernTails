import React, { useState } from 'react';
import '../LoginSignupNew.css';
import '../LoggedIn.css';
import HamsterWheel from '../components/HamsterWheel';
import LoggedInDashboard from '../components/LoggedInDashboard';
import { buildApiUrl } from '../api';

type Props = {
  initialMode?: 'login' | 'signup'
}

const LoginSignupAgent: React.FC<Props> = ({ initialMode = 'login' }) => {
  const [isSignup, setIsSignup] = useState(initialMode === 'signup');
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [signupName, setSignupName] = useState('');
  const [signupEmail, setSignupEmail] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [error, setError] = useState('');
  const [errorType, setErrorType] = useState<'error' | 'info'>('error');
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [autoLoginLoading, setAutoLoginLoading] = useState(() => Boolean(localStorage.getItem('access_token')));
  const [verificationToken, setVerificationToken] = useState('');
  const [unverifiedEmail, setUnverifiedEmail] = useState('');

  const setMessage = (msg: string, type: 'error' | 'info' = 'error') => {
    setError(msg);
    setErrorType(type);
  };

  React.useEffect(() => {
    setIsSignup(initialMode === 'signup')
  }, [initialMode])

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
    if (!token) {
      setAutoLoginLoading(false);
      return;
    }
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
      })
      .finally(() => {
        if (!canceled) setAutoLoginLoading(false);
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
    setMessage('');
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
      setMessage('Enter both email and password.');
      return;
    }
    setMessage('');
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
        setMessage('Email not verified - please enter the verification token sent to your email.', 'info');
      } else {
        setMessage(detailStr || 'Invalid credentials or user not found.');
      }
      return;
    }
    applyAuthResponse(data);
  };

  const handleSignup = async () => {
    setMessage('');
    setLoading(true);
    const cleanEmail = signupEmail.trim().toLowerCase();
    const cleanName = signupName.trim();
    const cleanPassword = signupPassword.trim();
    setSignupEmail(cleanEmail);
    setSignupName(cleanName);
    setSignupPassword(cleanPassword);
    if (!cleanEmail || !cleanName || !cleanPassword) {
      setLoading(false);
      setMessage('Email, display name, and password are required.');
      return;
    }
    const payload = { email: cleanEmail, password: cleanPassword, name: cleanName };
    const { data, errorDetail } = await performAuthRequest('/player/signup', payload);
    setLoading(false);
    if (errorDetail) {
      setMessage(formatDetail(errorDetail) || 'Signup failed.');
      return;
    }
    setIsSignup(false);
    setUnverifiedEmail(signupEmail);
    setVerificationToken(data?.verification_token || '');
    setMessage('Account created - verify your email before logging in (token included for dev).', 'info');
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
        setMessage('Email verified - you can now log in.', 'info');
        setUnverifiedEmail('');
        setVerificationToken('');
      } else {
        const err = await res.json();
        const detail = err.detail || err || '';
        const detailStr = formatDetail(detail);
        setMessage(detailStr || 'Verification failed');
      }
    } catch (e) {
      setLoading(false);
      setMessage('Network error during verification');
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
        setMessage('Verification token resent (returned for dev).', 'info');
      } else {
        const err = await res.json();
        const detail = err.detail || err || '';
        const detailStr = formatDetail(detail);
        setMessage(detailStr || 'Failed to resend verification');
      }
    } catch (e) {
      setLoading(false);
      setMessage('Network error during resend');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_email')
    localStorage.removeItem('user_username')
    localStorage.removeItem('tt:view')
    setProfile(null);
    setLoginEmail('');
    setLoginPassword('');
    setSignupName('');
    setSignupPassword('');
    setSignupEmail('');
    setIsSignup(false);
    setUnverifiedEmail('');
    setVerificationToken('');
  };

  if (autoLoginLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <HamsterWheel />
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh' }}>
      {loading && <HamsterWheel />}
      {!profile ? (
        <div className="tt-auth">
          <div className="tt-auth-bg" />
          <div className="tt-auth-inner">
            <div className="tt-auth-brand">
              <div className="tt-auth-tag">TavernTails</div>
              <h1 className="tt-auth-title">
                {isSignup ? 'Create your account' : 'Welcome back'}
              </h1>
            </div>

            <div className="tt-auth-card">
              {!isSignup ? (
                <section>
                  <h2 className="tt-auth-card-title">Sign In</h2>
                  <form onSubmit={e => { e.preventDefault(); handleLogin(); }} aria-busy={loading} aria-live="polite">
                    <div className="tt-auth-fields">
                      <div className="tt-auth-field">
                        <label className="tt-auth-label" htmlFor="loginEmail">Email</label>
                        <input id="loginEmail" className="tt-auth-input" type="email" placeholder="you@example.com" value={loginEmail} onChange={e => setLoginEmail(e.target.value)} autoComplete="email" />
                      </div>
                      <div className="tt-auth-field">
                        <label className="tt-auth-label" htmlFor="loginPassword">Password</label>
                        <input id="loginPassword" className="tt-auth-input" type="password" placeholder="••••••••" value={loginPassword} onChange={e => setLoginPassword(e.target.value)} autoComplete="current-password" />
                      </div>
                    </div>

                    <div className="tt-auth-actions">
                      <button className="btn" type="submit" disabled={loading} aria-disabled={loading}>
                        {loading ? 'Signing in…' : 'Sign In'}
                      </button>
                      <button type="button" className="btn btn-ghost" onClick={() => setIsSignup(true)}>
                        Create account
                      </button>
                    </div>

                    {error && (
                      <div className={`tt-auth-message tt-auth-message--${errorType}`} role="alert">
                        {error}
                      </div>
                    )}

                    {unverifiedEmail && (
                      <div className="tt-auth-verify">
                        <span className="tt-auth-verify-label">Enter the verification token sent to your email</span>
                        <label className="sr-only" htmlFor="verifyToken">Verification Token</label>
                        <input id="verifyToken" className="tt-auth-input" type="text" placeholder="Verification token" value={verificationToken} onChange={e => setVerificationToken(e.target.value)} />
                        <div className="tt-auth-verify-actions">
                          <button className="btn btn-sm" type="button" onClick={handleVerify}>Verify Email</button>
                          <button className="btn btn-sm btn-ghost" type="button" onClick={handleResendVerification}>Resend</button>
                        </div>
                      </div>
                    )}
                  </form>
                </section>
              ) : (
                <section>
                  <h2 className="tt-auth-card-title">Sign Up</h2>
                  <form onSubmit={e => { e.preventDefault(); handleSignup(); }}>
                    <div className="tt-auth-fields">
                      <div className="tt-auth-field">
                        <label className="tt-auth-label" htmlFor="signupEmail">Email</label>
                        <input id="signupEmail" className="tt-auth-input" type="email" placeholder="you@example.com" value={signupEmail} onChange={e => setSignupEmail(e.target.value)} autoComplete="email" />
                      </div>
                      <div className="tt-auth-field">
                        <label className="tt-auth-label" htmlFor="signupName">Display Name</label>
                        <input id="signupName" className="tt-auth-input" type="text" placeholder="Gandalf the Grey" value={signupName} onChange={e => setSignupName(e.target.value)} autoComplete="nickname" required />
                      </div>
                      <div className="tt-auth-field">
                        <label className="tt-auth-label" htmlFor="signupPassword">Password</label>
                        <input id="signupPassword" className="tt-auth-input" type="password" placeholder="••••••••" value={signupPassword} onChange={e => setSignupPassword(e.target.value)} autoComplete="new-password" />
                      </div>
                    </div>

                    <div className="tt-auth-actions">
                      <button className="btn" type="submit" disabled={loading} aria-disabled={loading}>
                        {loading ? 'Creating account…' : 'Create Account'}
                      </button>
                      <button type="button" className="btn btn-ghost" onClick={() => setIsSignup(false)}>
                        Sign In
                      </button>
                    </div>

                    {error && (
                      <div className={`tt-auth-message tt-auth-message--${errorType}`} role="alert">
                        {error}
                      </div>
                    )}
                  </form>
                </section>
              )}
            </div>
          </div>
        </div>
      ) : (
        <LoggedInDashboard profile={profile} onLogout={handleLogout} />
      )}
    </div>
  );
};

export default LoginSignupAgent;
