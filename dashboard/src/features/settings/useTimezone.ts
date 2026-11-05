import { browserTimezone } from "@/lib/zoned"
import { useRules } from "./useSettings"

export function useTimezone(): string {
  const { data } = useRules()
  return data?.timezone || browserTimezone()
}
