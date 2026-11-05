import { addDays, type WallTime } from "@/lib/zoned"
import type { DateOnly } from "./types"

export const HOUR_PX = 48
export const SNAP_MINUTES = 15
export const DAY_MINUTES = 1440

export function snap(minutes: number): number {
  return Math.round(minutes / SNAP_MINUTES) * SNAP_MINUTES
}

export function minuteAt(clientY: number, top: number): number {
  const minutes = snap(((clientY - top) / HOUR_PX) * 60)
  return Math.min(DAY_MINUTES, Math.max(0, minutes))
}

export function wallAt(day: DateOnly, minutes: number): WallTime {
  if (minutes >= DAY_MINUTES) return { ...addDays(day, 1), hour: 0, minute: 0 }
  return { ...day, hour: Math.floor(minutes / 60), minute: minutes % 60 }
}

export function pixels(minutes: number): number {
  return (minutes / 60) * HOUR_PX
}
