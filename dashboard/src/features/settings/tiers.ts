import type { ModelTier } from "./types"

export const tierLabels: Record<ModelTier, string> = {
  supported: "Quality",
  degraded: "Fast",
}

export const tierNotes: Record<ModelTier, string> = {
  supported: "Best answers; needs 16 GB",
  degraded: "Faster; lighter on memory",
}
