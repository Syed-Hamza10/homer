import { cn } from "@/lib/utils"

type Props = { role: "user" | "assistant"; content: string }

export function MessageBubble({ role, content }: Props) {
  const own = role === "user"
  return (
    <div className={cn("flex", own ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[75%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
          own ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        {content || <span className="animate-pulse">…</span>}
      </div>
    </div>
  )
}
