import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { nextStep, problemText, type Problem } from "@/lib/nextStep"
import { cn } from "@/lib/utils"

type Props = {
  error: Problem
  onRetry?: () => void
  className?: string
}

export function ErrorNotice({ error, onRetry, className }: Props) {
  const text = problemText(error)
  if (!text) return null
  const step = nextStep(error)
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-destructive",
        className,
      )}
    >
      <span>{text}</span>
      {step === "sign-in" && (
        <Button asChild size="xs" variant="outline">
          <Link to="/login">Sign in</Link>
        </Button>
      )}
      {step === "reconnect" && (
        <Button asChild size="xs" variant="outline">
          <Link to="/settings">Reconnect Google</Link>
        </Button>
      )}
      {step !== "sign-in" && onRetry && (
        <Button size="xs" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}
