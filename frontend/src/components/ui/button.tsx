import type { ButtonHTMLAttributes, Ref } from 'react'
import { cva } from 'class-variance-authority'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
const styles = cva('inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-200 active:translate-y-px disabled:opacity-50 disabled:active:translate-y-0', { variants: { variant: { default: 'bg-emerald-300 text-slate-950 hover:bg-emerald-200', outline: 'border border-slate-600 text-slate-200 hover:bg-slate-800' } }, defaultVariants: { variant: 'default' } })
export function Button({ className, variant, type = 'button', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'outline'; ref?: Ref<HTMLButtonElement> }) { return <button type={type} className={twMerge(clsx(styles({ variant }), className))} {...props}/> }
