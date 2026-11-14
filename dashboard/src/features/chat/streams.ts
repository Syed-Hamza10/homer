import { useSyncExternalStore } from "react"
import type { Problem } from "@/lib/nextStep"
import type { ActivityItem, ChoiceHint } from "./types"

export type Draft = { user: string; assistant: string }

export type Stream = {
  draft: Draft | null
  choice?: ChoiceHint
  items: ActivityItem[]
  status: string | null
  error: Problem
  failed: boolean
  controller: AbortController | null
}

type State = { streams: Record<string, Stream>; tokens: number }

export const NEW_CHAT = "new"

export const idle: Stream = {
  draft: null,
  items: [],
  status: null,
  error: null,
  failed: false,
  controller: null,
}

let state: State = { streams: {}, tokens: 0 }
const listeners = new Set<() => void>()

function publish(next: State) {
  state = next
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function patchStream(
  key: string,
  change: (stream: Stream) => Partial<Stream>,
) {
  const current = state.streams[key] ?? idle
  publish({
    ...state,
    streams: { ...state.streams, [key]: { ...current, ...change(current) } },
  })
}

export function moveStream(from: string, to: string) {
  const { [from]: moved, ...rest } = state.streams
  publish({ ...state, streams: { ...rest, [to]: moved ?? idle } })
}

export function addTokens(count: number) {
  publish({ ...state, tokens: state.tokens + count })
}

export const isLive = (stream: Stream): boolean =>
  stream.draft !== null && !stream.failed

export function useStreams(): State {
  return useSyncExternalStore(subscribe, () => state)
}

export function useReplying(): Set<string> {
  const { streams } = useStreams()
  return new Set(
    Object.entries(streams)
      .filter(([, stream]) => isLive(stream))
      .map(([key]) => key),
  )
}
