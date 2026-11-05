import { createSseParser, type SseHandlers } from "./sse"

export class ApiError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`Request failed with status ${status}`)
    this.status = status
  }
}

const jsonInit = (body: unknown, method = "POST"): RequestInit => ({
  method,
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

export async function post(url: string, body: unknown): Promise<void> {
  await send(url, jsonInit(body))
}

export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await send(url, jsonInit(body))
  return res.json() as Promise<T>
}

export async function putJson<T>(url: string, body: unknown): Promise<T> {
  const res = await send(url, jsonInit(body, "PUT"))
  return res.json() as Promise<T>
}

export async function patchJson<T>(url: string, body: unknown): Promise<T> {
  const res = await send(url, jsonInit(body, "PATCH"))
  return res.json() as Promise<T>
}

export async function del(url: string): Promise<void> {
  await send(url, { method: "DELETE" })
}

export async function streamSse(
  url: string,
  body: unknown,
  handlers: SseHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await send(url, {
    ...jsonInit(body),
    headers: { ...jsonInit(body).headers, Accept: "text/event-stream" },
    signal,
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
