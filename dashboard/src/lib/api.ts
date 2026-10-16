import { createSseParser, type SseHandlers } from "./sse"

export class ApiError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`Request failed with status ${status}`)
    this.status = status
  }
}

const jsonInit = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
})

async function send(url: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(url, { credentials: "same-origin", ...init })
  if (!res.ok) throw new ApiError(res.status)
  return res
}

export async function getJson<T>(url: string): Promise<T> {
  const res = await send(url)
  return res.json() as Promise<T>
}

export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await send(url, jsonInit(body))
  return res.json() as Promise<T>
}

export async function streamSse(
  url: string,
  body: unknown,
  handlers: SseHandlers,
): Promise<void> {
  const res = await send(url, {
    ...jsonInit(body),
    headers: { ...jsonInit(body).headers, Accept: "text/event-stream" },
  })
  if (!res.body) throw new ApiError(res.status)
  const parser = createSseParser(handlers)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    parser.push(decoder.decode(value, { stream: true }))
  }
}
