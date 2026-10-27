import { useState, type FormEvent } from 'react'
import { ShieldCheck } from 'lucide-react'
import { Button } from '../components/ui/button'

export function LoginPanel({ loading, error, onLogin }: { loading: boolean; error: string; onLogin: (email: string, password: string) => Promise<void> }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault()
    const supplied = password
    setPassword('')
    await onLogin(email, supplied)
  }
  return <section className="panel auth-panel"><ShieldCheck size={26}/><div><h3>Acesse sua carteira privada</h3><p>Entre com sua conta autorizada. A demonstração está disponível sem login.</p></div><form onSubmit={submit} aria-label="Login da carteira"><label>E-mail<input aria-label="E-mail" type="email" autoComplete="username" required value={email} disabled={loading} onChange={e => setEmail(e.target.value)}/></label><label>Senha<input aria-label="Senha" type="password" autoComplete="current-password" required value={password} disabled={loading} onChange={e => setPassword(e.target.value)}/></label><Button type="submit" disabled={loading}>{loading ? 'Verificando sessão…' : 'Entrar'}</Button></form>{error && <p role="alert" className="negative">{error}</p>}</section>
}
