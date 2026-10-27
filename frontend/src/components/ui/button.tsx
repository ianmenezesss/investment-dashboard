import type { ButtonHTMLAttributes } from 'react'
import { cva } from 'class-variance-authority'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
const styles = cva('inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors disabled:opacity-40', { variants: { variant: { default: 'bg-emerald-300 text-slate-950 hover:bg-emerald-200', outline: 'border border-slate-700 text-slate-200 hover:bg-slate-800' } }, defaultVariants: { variant: 'default' } })
export function Button({ className, variant, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'outline' }) { return <button className={twMerge(clsx(styles({ variant }), className))} {...props}/> }
