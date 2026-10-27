import { useState, type FormEvent } from 'react'
import { ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole } from 'lucide-react'
import { Button } from '../components/ui/button'

export function LoginPanel({ loading, error, onLogin, local = false, onLocalLogin }: { loading: boolean; error: string; onLogin: (email: string, password: string) => Promise<void>; local?: boolean; onLocalLogin?: (token: string) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (loading) return
    const supplied = password
    setPassword('')
    if (local) onLocalLogin?.(supplied)
    else await onLogin(email, supplied)
  }
  return <form onSubmit={submit} aria-label="Login da carteira" className="login-form">
    {!local && <label htmlFor="login-email">E-mail<input id="login-email" type="email" placeholder="voce@exemplo.com" autoComplete="username" required value={email} disabled={loading} onChange={e => setEmail(e.target.value)}/></label>}
    <label htmlFor="login-password">{local ? 'Token de desenvolvimento' : 'Senha'}<span className="password-field"><LockKeyhole size={17}/><input id="login-password" type={visible ? 'text' : 'password'} placeholder={local ? 'Seu token local' : 'Sua senha'} autoComplete={local ? 'off' : 'current-password'} required value={password} disabled={loading} onChange={e => setPassword(e.target.value)}/><button type="button" aria-label={visible ? 'Ocultar senha' : 'Mostrar senha'} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18}/> : <Eye size={18}/>}</button></span></label>
    {error && <div role="alert" className="login-error">{error}</div>}
    <Button type="submit" disabled={loading} className="login-submit">{loading ? <><LoaderCircle size={18} className="spin"/> Verificando acesso…</> : <>Entrar na minha carteira <ArrowRight size={17}/></>}</Button>
    {local && <p className="login-local-note">Acesso local exclusivo para desenvolvimento.</p>}
  </form>
}
