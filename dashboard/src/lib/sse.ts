export type SseHandlers = Record<string, (data: unknown) => void>

function parseFrame(frame: string): { event: string; data: string } | null {
  let event = ""
  const data: string[] = []
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim()
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart())
  }
  if (!event || data.length === 0) return null
  return { event, data: data.join("\n") }
}

export function createSseParser(handlers: SseHandlers) {
  let buffer = ""
  return {
    push(chunk: string) {
      buffer += chunk.replaceAll("\r\n", "\n")
      const frames = buffer.split("\n\n")
      buffer = frames.pop() ?? ""
      for (const raw of frames) {
        const frame = parseFrame(raw)
        const handler = frame && handlers[frame.event]
        if (frame && handler) handler(JSON.parse(frame.data))
      }
    },
  }
}
