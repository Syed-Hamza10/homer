export type ModelTier = "supported" | "degraded"

export type ClientRules = {
  name?: string | null
  signature: string
  tone: string
  business_hours: string
  follow_up_days: number
  priority_contacts: string[]
  email_to_self: boolean
  self_email: string
  model_tier: ModelTier | null
  timezone: string
}

export type TierOption = {
  tier: ModelTier
  tag: string
  context: number
}

export type ModelOptions = {
  selected_tier: ModelTier | null
  effective_tier: ModelTier
  tiers: TierOption[]
}

export type SmokeResult = {
  ok: boolean
  text: string
  error: string
  latency_ms: number
}

export type SelfEmailStatus = "off" | "ok" | "mismatch" | "unknown"

export type Health = {
  status: string
  version: string
  ollama: "ok" | "down"
  model: string
  model_status: "running" | "stopped" | "missing"
  servers: Record<string, "ok" | "down">
  self_email: SelfEmailStatus
}

export type GoogleState = "not_connected" | "connected" | "expiring" | "expired"

export type GoogleStatus = {
  state: GoogleState
  email: string | null
  connected_at: string | null
  days_left: number | null
  connecting: boolean
  client_secret_found: boolean
  client_secret_path: string
}

export type SearchProvider = "duckduckgo" | "brave" | "tavily"

export type KeyedProvider = "brave" | "tavily"

export type SearchSettings = {
  provider: SearchProvider
  api_provider: KeyedProvider
  fallback: boolean
  key_hint: string | null
  hosts: string[]
}

export type SearchUpdate = {
  provider: SearchProvider
  api_provider: KeyedProvider
  fallback: boolean
  api_key?: string
}

export type SearchProbe = {
  status: "ok" | "blocked" | "invalid_key" | "limited" | "failed" | "off"
  provider: string
  results: number
}
