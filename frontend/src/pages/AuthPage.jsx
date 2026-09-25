import { useState } from 'react'
import { Link } from '../components/ui/primitives'
import { useAuth } from '../state/authContext'
import { navigate } from '../lib/router'
import '../styles/auth.css'

export default function AuthPage({ mode = 'signin' }) {
  const isSignup = mode === 'signup'
  const { authenticate } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      await authenticate(mode, { email, password, ...(isSignup ? { display_name: displayName } : {}) })
      navigate('/ask-ai')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return <main className="auth-page">
    <section className="auth-card card card-pad" aria-labelledby="auth-title">
      <Link to="/" className="auth-brand" aria-label="QueryLens home"><span className="auth-mark">Q</span><span>QueryLens</span></Link>
      <span className="eyebrow">Your analysis workspace</span>
      <h1 id="auth-title">{isSignup ? 'Create your account' : 'Welcome back'}</h1>
      <p className="auth-intro">{isSignup ? 'Save your conversations and return to your analyses whenever you need them.' : 'Sign in to continue to your saved conversations and datasets.'}</p>

      <form className="auth-form" onSubmit={submit}>
        {isSignup && <label className="auth-field"><span>Name</span><input className="input" autoComplete="name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={80} placeholder="Your name" /></label>}
        <label className="auth-field"><span>Email</span><input className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></label>
        <label className="auth-field"><span>Password</span><input className="input" type="password" autoComplete={isSignup ? 'new-password' : 'current-password'} required minLength={isSignup ? 8 : 1} value={password} onChange={(e) => setPassword(e.target.value)} placeholder={isSignup ? 'At least 8 characters' : 'Your password'} /></label>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button className="btn btn-primary auth-submit" type="submit" disabled={busy}>{busy ? 'Please wait…' : isSignup ? 'Create account' : 'Sign in'}</button>
      </form>

      <p className="auth-switch">{isSignup ? 'Already have an account?' : 'New to QueryLens?'} <Link to={isSignup ? '/signin' : '/signup'}>{isSignup ? 'Sign in' : 'Create an account'}</Link></p>
      <div className="auth-storage-note"><strong>Use QueryLens without an account</strong><span>All analysis features are available. Chats and uploaded files are kept only in temporary session memory and aren’t saved to your account history.</span></div>
      <Link to="/ask-ai" className="auth-guest-link">Continue without signing in</Link>
    </section>
  </main>
}
