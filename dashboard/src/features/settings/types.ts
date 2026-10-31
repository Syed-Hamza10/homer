export type ModelTier = "supported" | "degraded"

export type ClientRules = {
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
  servers: Record<string, "ok" | "down">
  self_email: SelfEmailStatus
}
