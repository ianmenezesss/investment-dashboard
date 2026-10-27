import { useRef } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { LoaderCircle, RotateCcw, Trash2 } from 'lucide-react'
import { Button } from './button'

type Props = {
  open: boolean; onClose: () => void; onConfirm: () => Promise<void>
  title: string; description: string; confirmLabel: string
  kind: 'reset' | 'delete'; busy: boolean; error: string; returnFocus: HTMLElement | null
}
export function ConfirmDialog(props: Props) {
  const cancel = useRef<HTMLButtonElement>(null)
  const Icon = props.kind === 'reset' ? RotateCcw : Trash2
  return <Dialog.Root open={props.open} onOpenChange={open => { if (!open && !props.busy) props.onClose() }}><Dialog.Portal><Dialog.Overlay className="overlay confirm-overlay"/><Dialog.Content role="alertdialog" className="modal confirm-dialog" onOpenAutoFocus={event => { event.preventDefault(); cancel.current?.focus() }} onCloseAutoFocus={event => { event.preventDefault(); props.returnFocus?.focus() }} onEscapeKeyDown={event => { if (props.busy) event.preventDefault() }} onPointerDownOutside={event => { if (props.busy) event.preventDefault() }}>
    <div className={`confirm-icon ${props.kind}`}><Icon size={23}/></div>
    <Dialog.Title>{props.title}</Dialog.Title><Dialog.Description>{props.description}</Dialog.Description>
    {props.error && <p className="login-error" role="alert">{props.error}</p>}
    <div className="confirm-actions"><Button ref={cancel} variant="outline" disabled={props.busy} onClick={props.onClose}>Cancelar</Button><Button disabled={props.busy} onClick={() => { void props.onConfirm() }} className={props.kind === 'delete' ? 'delete-confirm' : ''}>{props.busy ? <LoaderCircle size={16} className="spin"/> : <Icon size={16}/>} {props.busy ? 'Processando…' : props.confirmLabel}</Button></div>
  </Dialog.Content></Dialog.Portal></Dialog.Root>
}
