import type { Health, ModelStatus } from "./types"

const serviceNames: Record<string, string> = {
  google: "Google",
  search: "Web search",
}

const modelLabels: Record<ModelStatus, string> = {
  running: "Model running",
  stopped: "The AI model isn't running",
  missing: "The AI model is missing",
}

function ago(value: string, now: number): string {
  const minutes = Math.floor((now - new Date(value).getTime()) / 60000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `${hours} h ago` : "over a day ago"
}

export function healthLine(
  health: Health | null | undefined,
  now: number = Date.now(),
): string | null {
  if (!health) return null
  const problems = [
    ...Object.entries(health.servers)
      .filter(([, status]) => status === "down")
      .map(([name]) => `${serviceNames[name] ?? name} is not responding`),
    ...(health.self_email === "mismatch"
      ? ["Emails to yourself are paused"]
      : []),
  ]
  const others = problems.length ? problems : ["All systems OK"]
  const parts = [modelLabels[health.model_status], ...others]
  return `${parts.join(" · ")} · checked ${ago(health.checked_at, now)}`
}
