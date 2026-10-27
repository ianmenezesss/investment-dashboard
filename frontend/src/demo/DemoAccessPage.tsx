import { Link } from 'react-router-dom'
import { ChartNoAxesCombined, ShieldCheck } from 'lucide-react'

// O build público não recebe credenciais nem cria cliente Supabase.
export function DemoAccessPage() {
  return <div className="login-page"><section className="login-story"><Link className="brand" to="/"><ChartNoAxesCombined/> investment.</Link><div className="login-story-content"><h1>Seu patrimônio.<br/><em>Seu espaço privado.</em></h1></div></section><main className="login-main"><div className="login-card"><div className="login-lock"><ShieldCheck/></div><h2>Acesso à carteira privada</h2><p className="login-description">Este endereço oferece somente a demonstração pública. Para acessar seus investimentos reais, abra o ambiente privado do Investment Dashboard.</p><p className="login-description">Nenhuma senha é solicitada ou enviada por esta demonstração.</p><Link className="login-demo" to="/">Voltar à demonstração</Link></div></main></div>
}
