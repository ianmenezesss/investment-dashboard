import { ArrowUpRight, ChartNoAxesCombined, ShieldCheck, Layers3, Fingerprint } from 'lucide-react'
import { LoginPanel } from './LoginPanel'
import './login.css'

type Props = {
  loading: boolean; error: string; onLogin: (email: string, password: string) => Promise<void>
  onDemo: () => void; local: boolean; onLocalLogin: (token: string) => void
  connected?: boolean; onLogout: () => void
}
export function LoginPage(props: Props) {
  return <div className="login-page">
    <section className="login-story" aria-label="Investment Dashboard">
      <a className="brand login-brand" href="/login"><span className="brand-icon"><ChartNoAxesCombined size={28}/></span>investment<span className="brand-dot">.</span></a>
      <div className="login-story-content"><span className="login-kicker"><span/> SEU PATRIMÔNIO, EM PERSPECTIVA</span><h1>Mais clareza hoje.<br/><em>Mais possibilidades</em><br/>amanhã.</h1><p>Um espaço para acompanhar suas escolhas e construir o seu futuro. Com organização, privacidade e propósito.</p>
        <div className="login-art" aria-hidden="true"><div className="art-grid"/><svg viewBox="0 0 520 150" fill="none"><defs><linearGradient id="login-fill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#6ee7b7" stopOpacity=".2"/><stop offset="1" stopColor="#6ee7b7" stopOpacity="0"/></linearGradient></defs><path d="M0 130L50 115L100 120L150 85L200 95L250 65L300 75L350 38L400 50L450 18L520 5V150H0Z" fill="url(#login-fill)"/><path d="M0 130L50 115L100 120L150 85L200 95L250 65L300 75L350 38L400 50L450 18L520 5" stroke="#6ee7b7" strokeWidth="2.5"/></svg><span>ORGANIZE. ACOMPANHE. EVOLUA.</span></div>
      </div>
      <div className="login-principles"><span><ShieldCheck size={17}/> Acesso protegido</span><span><Layers3 size={17}/> Visão integrada</span><span><Fingerprint size={17}/> Seu espaço</span></div>
    </section>
    <main className="login-main"><div className="login-card"><div className="login-lock"><ShieldCheck size={24}/></div><p className="login-eyebrow">BEM-VINDO AO SEU PRÓXIMO PASSO</p><h2>Sua carteira começa aqui.</h2><p className="login-description">Entre para acompanhar seus investimentos<br/>com uma visão mais clara.</p>
      <LoginPanel loading={props.loading} error={props.error} onLogin={props.onLogin} local={props.local} onLocalLogin={props.onLocalLogin}/>
      {props.connected && <button className="login-other-account" onClick={props.onLogout}>Sair e usar outra conta</button>}
      <div className="login-divider"><span/>ou conheça primeiro<span/></div><button className="login-demo" onClick={props.onDemo}>Explorar demonstração <ArrowUpRight size={17}/></button><p className="login-demo-note">Sem login. Apenas dados fictícios.</p>
    </div><footer className="login-footer"><ShieldCheck size={13}/> Seu patrimônio é pessoal. Seu acesso também.</footer></main>
  </div>
}
