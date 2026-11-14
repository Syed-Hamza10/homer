export type HostUsage = { host: string; calls: number; last_seen: string }

export type HostsResponse = {
  hosts: HostUsage[]
  web_search: boolean
  web_search_configured: boolean
  search_hosts: string[]
}

export type WebSearchResponse = {
  enabled: boolean
  restart_required: boolean
}

export type WipeResponse = { deleted: Record<string, number> }

export type UsageResponse = {
  input_tokens: number
  output_tokens: number
  requests: number
  spent_usd: number
}
