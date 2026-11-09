import { CalendarPlus, Mail, ShieldCheck } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { ApprovalEditor } from "./ApprovalEditor"
import {
  approvalTitle,
  eventFields,
  mailFields,
  primaryLabel,
  statusLabel,
} from "./editable"
import { describeDecisionError, useDecide } from "./useDecide"
import { useEditApproval } from "./useEditApproval"
import type { Approval, PendingApproval } from "./types"

type Props = {
  approval: PendingApproval
  onDecided?: (approval: Approval) => void
}

function resultText(result: unknown): string | null {
  if (result && typeof result === "object" && "error" in result) {
    return String((result as { error: unknown }).error)
  }
  return null
}

const icons = { mail_send: Mail, cal_create: CalendarPlus }

export function ApprovalCard({ approval, onDecided }: Props) {
  const [current, setCurrent] = useState<PendingApproval>(approval)
  const [editing, setEditing] = useState(false)
  const decide = useDecide(onDecided)
  const edit = useEditApproval((fresh) => {
    setCurrent(fresh)
    setEditing(false)
  })
  const status = decide.data?.status ?? approval.status ?? "pending"
  const problem = resultText(decide.data?.result ?? approval.result)
  const error = describeDecisionError(decide.error ?? edit.error)
  const mail = mailFields(current)
  const editable = mail ?? eventFields(current)
  const busy = decide.isPending || edit.isPending
  const Icon = icons[current.action as keyof typeof icons] ?? ShieldCheck
  const settled = status !== "pending"

  return (
    <article
      id={`approval-${current.id}`}
      data-testid={`approval-${current.id}`}
      aria-label={approvalTitle(current)}
      className="animate-enter overflow-hidden rounded-xl border border-border bg-card text-card-foreground shadow-[0_1px_2px_oklch(0_0_0/0.04),inset_0_1px_0_var(--marble-1)]"
    >
      <header className="flex items-center gap-3 border-b border-border/80 px-4 py-3">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
          <Icon aria-hidden className="size-3.5" strokeWidth={1.8} />
        </span>
        <h3 className="min-w-0 flex-1 truncate font-heading text-[17px] leading-tight">
          {approvalTitle(current)}
        </h3>
        <span aria-live="polite">
          {settled && (
            <span
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-xs font-medium",
                status === "done"
                  ? "border-brand/30 bg-brand/10 text-foreground"
                  : "border-border bg-muted text-muted-foreground",
              )}
            >
              {statusLabel(current.action, status)}
            </span>
          )}
        </span>
      </header>
      <div className="px-4 py-3.5">
        {editing && editable ? (
          <ApprovalEditor
            initial={editable}
            saving={edit.isPending}
            onSave={(change) => edit.mutate({ id: current.id, change })}
            onCancel={() => setEditing(false)}
          />
        ) : mail ? (
          <div className={cn("flex flex-col gap-2", settled && "opacity-75")}>
            <p className="text-xs text-muted-foreground">To {mail.to}</p>
            {mail.subject && (
              <p className="text-[15px] font-medium">{mail.subject}</p>
            )}
            <p className="max-h-80 overflow-y-auto text-sm leading-relaxed whitespace-pre-wrap">
              {mail.body}
            </p>
          </div>
        ) : (
          <p
            className={cn(
              "text-sm leading-relaxed whitespace-pre-wrap",
              settled && "opacity-75",
            )}
          >
            {current.preview}
          </p>
        )}
        {problem && (
          <p className="mt-2 text-sm text-muted-foreground">{problem}</p>
        )}
        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
      </div>
      {!settled && !editing && (
        <footer className="flex items-center gap-1.5 border-t border-border/80 bg-muted/40 px-4 py-2.5">
          <Button
            variant="brand"
            disabled={busy}
            onClick={() =>
              decide.mutate({ id: current.id, decision: "approve" })
            }
            className="px-4"
          >
            {primaryLabel(current.action)}
          </Button>
          {editable && (
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => setEditing(true)}
            >
              Edit
            </Button>
          )}
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() =>
              decide.mutate({ id: current.id, decision: "reject" })
            }
            className="text-muted-foreground"
          >
            Discard
          </Button>
        </footer>
      )}
    </article>
  )
}
