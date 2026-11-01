import { cn } from "@/lib/utils"

type Props = { role: "user" | "assistant"; content: string }

export function MessageBubble({ role, content }: Props) {
  const own = role === "user"
  return (
    <div
      className={cn("flex", own ? "justify-end" : "justify-start")}
      data-testid={`message-${role}`}
    >
      <div
        className={cn(
          "max-w-[75%] rounded-md px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
          own
            ? "bg-primary text-primary-foreground shadow-[inset_0_1px_0_oklch(1_0_0/0.12)]"
            : "border border-border bg-card/80 shadow-[inset_0_1px_0_var(--marble-1)]",
        )}
      >
        {content || <span className="animate-pulse">…</span>}
      </div>
    </div>
  )
}
