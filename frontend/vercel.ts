import { selectVercelConfig } from './deployment/vercel-config'

// Evaluated by Vercel before the build, separately for each project/environment.
// Never load .env.local here or rewrite configuration files during npm build.
export const config = selectVercelConfig(process.env)
