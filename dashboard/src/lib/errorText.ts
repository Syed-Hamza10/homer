import { ApiError } from "@/lib/api"

export function errorText(error: Error | null): string | null {
  if (!error) return null
  if (error instanceof ApiError && error.status === 502)
    return "Google could not be reached. Try again, or reconnect Google in Settings."
  if (error instanceof ApiError && error.status === 422)
    return "Nothing to change, or a field is not valid."
  if (error instanceof ApiError) return `Request failed (${error.status})`
  return "Cannot reach the Homer server"
}
