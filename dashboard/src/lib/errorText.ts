import { ApiError } from "@/lib/api"

export function errorText(error: Error | null): string | null {
  if (!error) return null
  if (error instanceof ApiError) return error.message
  return "Cannot reach the Homer server. Check that Homer is running."
}
