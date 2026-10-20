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
