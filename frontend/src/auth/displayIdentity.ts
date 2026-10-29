type SessionDisplayUser = {
  email?: string | null
  user_metadata?: Record<string, unknown> | null
} | null | undefined

const nonEmptyString = (value: unknown): string | null => typeof value === 'string' && value.trim() ? value.trim() : null

/** Presentation only: identity and authorization continue to use the verified Supabase user id. */
export function getDisplayIdentity(user: SessionDisplayUser): { name: string; initial: string } {
  const metadata = user?.user_metadata
  const name = nonEmptyString(metadata?.full_name)
    ?? nonEmptyString(metadata?.name)
    ?? nonEmptyString(metadata?.display_name)
    ?? nonEmptyString(user?.email?.split('@')[0])
    ?? 'Investidor'
  const firstGrapheme = name.trim().match(/^\P{M}\p{M}*/u)?.[0] ?? Array.from(name.trim())[0] ?? 'I'
  return { name, initial: firstGrapheme.toLocaleUpperCase('pt-BR') }
}
