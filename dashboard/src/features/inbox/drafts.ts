import type { ComposeDraft } from "./types"

export type SavedDraft = ComposeDraft & { title: string }

export const NEW_MESSAGE = "new"

const keyOf = (slot: string) => `homer.draft.${slot}`

export function loadDraft(slot: string): SavedDraft | null {
  try {
    const raw = localStorage.getItem(keyOf(slot))
    return raw ? (JSON.parse(raw) as SavedDraft) : null
  } catch {
    return null
  }
}

export function saveDraft(slot: string, draft: SavedDraft) {
  try {
    localStorage.setItem(keyOf(slot), JSON.stringify(draft))
  } catch {
    return
  }
}

export function clearDraft(slot: string) {
  try {
    localStorage.removeItem(keyOf(slot))
  } catch {
    return
  }
}
