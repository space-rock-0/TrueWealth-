import React, { useEffect, useRef, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import client from '../api/client';

export default function AuthPage({ onAuthenticated }) {
  const onAuthenticatedRef = useRef(onAuthenticated);
  onAuthenticatedRef.current = onAuthenticated;
  const [mode, setMode] = useState('login');
  const [identifier, setIdentifier] = useState('');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const ensureCsrf = async () => client.get('/auth/csrf');
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const verifyToken = params.get('verify_token');
    const resetToken = params.get('reset_token');
    if (verifyToken) {
      setBusy(true);
      ensureCsrf().then(() => client.post('/auth/verify-email', { token: verifyToken }))
        .then(({ data }) => onAuthenticatedRef.current(data))
        .catch((e) => setError(e.response?.data?.detail || 'Email verification failed.'))
        .finally(() => setBusy(false));
      window.history.replaceState({}, '', window.location.pathname);
    } else if (resetToken) {
      setIdentifier(resetToken);
      setMode('reset');
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    setError(''); setNotice(''); setBusy(true);
    try {
      await ensureCsrf();
      if (mode === 'register') {
        if (password !== confirm) throw new Error('Passwords do not match.');
        const { data } = await client.post('/auth/register', { email, username, password });
        if (data.id) onAuthenticated(data);
        else setNotice(data.message);
      } else if (mode === 'login') {
        const { data } = await client.post('/auth/login', { identifier, password });
        onAuthenticated(data);
      } else if (mode === 'forgot') {
        const { data } = await client.post('/auth/forgot-password', { email });
        setNotice(data.message);
      } else {
        if (password !== confirm) throw new Error('Passwords do not match.');
        const { data } = await client.post('/auth/reset-password', { token: identifier, password });
        setNotice(data.message); setMode('login'); setIdentifier(''); setPassword(''); setConfirm('');
      }
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Could not complete this request.');
    } finally { setBusy(false); }
  };

  const resendVerification = async () => {
    setBusy(true); setError('');
    try {
      await ensureCsrf();
      const { data } = await client.post('/auth/resend-verification', { email });
      setNotice(data.message);
    } catch (e) { setError(e.response?.data?.detail || 'Could not resend the verification email.'); }
    finally { setBusy(false); }
  };

  const title = mode === 'register' ? 'Create your account' : mode === 'forgot' ? 'Reset your password' : mode === 'reset' ? 'Choose a new password' : 'Welcome back';
  return (
    <main className="min-h-screen flex items-center justify-center bg-slate-950 px-4 py-10 text-slate-100">
      <section className="w-full max-w-md rounded-3xl border border-white/10 bg-slate-900/90 p-8 shadow-2xl">
        <div className="mb-7 flex items-center gap-3"><div className="rounded-xl bg-blue-500/20 p-3 text-blue-300"><ShieldCheck /></div><div><h1 className="text-2xl font-bold">TrueWealth AI</h1><p className="text-sm text-slate-400">{title}</p></div></div>
        <form className="space-y-4" onSubmit={submit}>
          {mode === 'register' && <>
            <label className="block text-sm">Email<input required type="email" autoComplete="email" maxLength={254} value={email} onChange={e => setEmail(e.target.value)} className="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 outline-none focus:border-blue-400" /></label>
            <label className="block text-sm">Username<input required minLength={3} maxLength={32} pattern="[A-Za-z0-9_]+" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} className="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 outline-none focus:border-blue-400" /></label>
          </>}
          {mode === 'login' && <label className="block text-sm">Email or username<input required autoComplete="username" value={identifier} onChange={e => setIdentifier(e.target.value)} className="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 outline-none focus:border-blue-400" /></label>}
          {mode === 'forgot' && <label className="block text-sm">Account email<input required type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} className="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 outline-none focus:border-blue-400" /></label>}
          {mode === 'reset' && <p className="break-all text-xs text-slate-400">One-time reset token: {identifier.slice(0, 12)}…</p>}
          {['login', 'register', 'reset'].includes(mode) && <label className="block text-sm">{mode === 'reset' ? 'New password' : 'Password'}<input required type="password" minLength={mode === 'login' ? 1 : 12} maxLength={128} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={e => setPassword(e.target.value)} className="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 outline-none focus:border-blue-400" />{mode !== 'login' && <span className="mt-1 block text-xs text-slate-500">Use at least 12 characters.</span>}</label>}
          {['register', 'reset'].includes(mode) && <label className="block text-sm">Confirm password<input required type="password" minLength={12} maxLength={128} autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} className="mt-1 w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 outline-none focus:border-blue-400" /></label>}
          {error && <p role="alert" className="rounded-lg bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}
          {notice && <p role="status" className="rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-300">{notice}</p>}
          {mode === 'register' && notice && <button type="button" onClick={resendVerification} disabled={busy} className="w-full text-sm text-blue-300 hover:text-blue-200">Resend verification email</button>}
          <button disabled={busy} className="w-full rounded-xl bg-blue-600 px-4 py-3 font-semibold hover:bg-blue-500 disabled:opacity-60">{busy ? 'Please wait…' : title}</button>
        </form>
        <div className="mt-5 flex flex-wrap justify-between gap-3 text-sm text-blue-300">
          {mode === 'login' ? <><button onClick={() => {setMode('register');setError('');setNotice('');}}>Create account</button><button onClick={() => {setMode('forgot');setError('');setNotice('');}}>Forgot password?</button></> : <button onClick={() => {setMode('login');setError('');setNotice('');}}>Back to sign in</button>}
        </div>
      </section>
    </main>
  );
}
