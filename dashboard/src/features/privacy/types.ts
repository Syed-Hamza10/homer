export type HostUsage = { host: string; calls: number; last_seen: string }

export type HostsResponse = { hosts: HostUsage[]; web_search: boolean }

export type UsageResponse = {
  input_tokens: number
  output_tokens: number
  requests: number
  spent_usd: number
}
