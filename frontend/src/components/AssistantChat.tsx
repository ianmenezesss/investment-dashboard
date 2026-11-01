import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import { ArrowUp, Sparkles, X } from 'lucide-react'
import { askAssistant, type AssistantScreenContext } from '../api'
import './assistant.css'

const suggestions = ['O que é CDB?', 'Como funciona o CDI?', 'Como usar o dashboard?']
const welcome = 'Olá! Sou a Íris, sua assistente de educação financeira. Posso ajudar você a entender conceitos financeiros e utilizar as ferramentas do Investment Dashboard. O que gostaria de saber?'

type Message = { role: 'user' | 'assistant'; text: string; error?: boolean }
type ViewportStyle = CSSProperties & {
  '--iris-viewport-height'?: string
  '--iris-viewport-top'?: string
}

export function AssistantChat({ token, context = 'overview' }: { token: string; context?: AssistantScreenContext }) {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [viewport, setViewport] = useState<{ height: number; offsetTop: number }>()
  const launcherRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wasOpen = useRef(false)

  useEffect(() => {
    const visualViewport = window.visualViewport
    if (!visualViewport) return
    const updateViewport = () => setViewport({ height: visualViewport.height, offsetTop: visualViewport.offsetTop })
    updateViewport()
    visualViewport.addEventListener('resize', updateViewport)
    visualViewport.addEventListener('scroll', updateViewport)
    return () => {
      visualViewport.removeEventListener('resize', updateViewport)
      visualViewport.removeEventListener('scroll', updateViewport)
    }
  }, [])

  useEffect(() => {
    if (open) panelRef.current?.focus()
    else if (wasOpen.current) launcherRef.current?.focus()
    wasOpen.current = open
  }, [open])

  useEffect(() => {
    const end = messagesEndRef.current
    if (open && end && typeof end.scrollIntoView === 'function') {
      end.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [messages, busy, open])

  async function send(text = input) {
    const message = text.trim()
    if (!message || busy || message.length > 1000) return
    setInput('')
    setMessages(current => [...current, { role: 'user', text: message }])
    setBusy(true)
    try {
      const answer = await askAssistant(message, token, context)
      setMessages(current => [...current, { role: 'assistant', text: answer }])
    } catch (error) {
      const text = error instanceof Error ? error.message : 'A Íris está indisponível. Tente novamente mais tarde.'
      setMessages(current => [...current, { role: 'assistant', text, error: true }])
    } finally {
      setBusy(false)
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void send()
  }

  const viewportStyle: ViewportStyle | undefined = viewport ? {
    '--iris-viewport-height': `${viewport.height}px`,
    '--iris-viewport-top': `${viewport.offsetTop}px`,
  } : undefined

  return <div className="iris-root" style={viewportStyle}>
    {open && <section
      ref={panelRef}
      id="iris-chat-panel"
      className="iris-panel"
      role="dialog"
      aria-labelledby="iris-chat-title"
      aria-modal="false"
      tabIndex={-1}
      onKeyDown={event => {
        if (event.key === 'Escape') {
          event.stopPropagation()
          setOpen(false)
        }
      }}
    >
      <header className="iris-header">
        <span className="iris-mark" aria-hidden="true"><Sparkles size={19}/></span>
        <div className="iris-heading">
          <h2 id="iris-chat-title">Íris</h2>
          <p>Assistente de educação financeira</p>
        </div>
        <button className="iris-close" type="button" aria-label="Fechar conversa com Íris" onClick={() => setOpen(false)}>
          <X size={19} aria-hidden="true"/>
        </button>
      </header>

      <div className="iris-messages" role="log" aria-live="polite" aria-relevant="additions">
        {!messages.length ? <div className="iris-welcome">
          <p className="iris-greeting">{welcome}</p>
          <div className="iris-suggestions" aria-label="Sugestões de perguntas">
            {suggestions.map(suggestion => <button key={suggestion} type="button" disabled={busy} onClick={() => void send(suggestion)}>
              {suggestion}<ArrowUp size={14} aria-hidden="true"/>
            </button>)}
          </div>
        </div> : messages.map((message, index) => <div
          key={`${message.role}-${index}`}
          className={`iris-message iris-message--${message.role}${message.error ? ' iris-message--error' : ''}`}
          role={message.error ? 'alert' : undefined}
        >
          <span className="iris-message-label">{message.role === 'user' ? 'Você' : 'Íris'}</span>
          <p>{message.text}</p>
        </div>)}
        {busy && <p className="iris-loading" role="status"><span aria-hidden="true"/>Íris está preparando uma resposta…</p>}
        <div ref={messagesEndRef}/>
      </div>

      <form className="iris-composer" onSubmit={submit}>
        <label className="iris-sr-only" htmlFor="iris-question">Sua pergunta para a Íris</label>
        <input
          id="iris-question"
          type="text"
          maxLength={1000}
          value={input}
          onChange={event => setInput(event.target.value)}
          placeholder="Escreva sua pergunta…"
          autoComplete="off"
        />
        <button type="submit" disabled={busy || !input.trim()} aria-label="Enviar pergunta">
          <ArrowUp size={18} aria-hidden="true"/>
        </button>
      </form>
      <p className="iris-disclaimer">Respostas educativas. Suas perguntas são enviadas à Groq para resposta; não inclua informações pessoais ou financeiras. A Íris não acessa sua carteira.</p>
    </section>}
    <button
      ref={launcherRef}
      className="iris-launcher"
      type="button"
      aria-label={open ? 'Fechar conversa com Íris' : 'Abrir conversa com Íris'}
      aria-expanded={open}
      aria-controls={open ? 'iris-chat-panel' : undefined}
      aria-haspopup="dialog"
      onClick={() => setOpen(current => !current)}
    >
      {open ? <X size={21} aria-hidden="true"/> : <Sparkles size={21} aria-hidden="true"/>}
      <span className="iris-launcher-label">Íris</span>
    </button>
  </div>
}
