import { ApiError, RECONNECT_DETAIL } from "./api"
import { errorText } from "./errorText"

export type Problem = Error | string | null | undefined

export type NextStep = "sign-in" | "reconnect" | "retry"

export function problemText(problem: Problem): string | null {
  if (!problem) return null
  return typeof problem === "string" ? problem : errorText(problem)
}

export function nextStep(problem: Problem): NextStep {
  if (problem instanceof ApiError && problem.status === 401) return "sign-in"
  if (problem instanceof ApiError && problem.detail.includes(RECONNECT_DETAIL))
    return "reconnect"
  if (typeof problem === "string" && /reconnect/i.test(problem))
    return "reconnect"
  return "retry"
}
