import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ApprovalEditor } from "./ApprovalEditor"
import { eventFields, mailFields, primaryLabel } from "./editable"
import { describeDecisionError, useDecide } from "./useDecide"
import { useEditApproval } from "./useEditApproval"
import type { Approval, PendingApproval } from "./types"

type Props = {
  approval: PendingApproval
  onDecided?: (approval: Approval) => void
}

function resultText(approval: Approval): string | null {
  const result = approval.result
  if (result && typeof result === "object" && "error" in result) {
    return String((result as { error: unknown }).error)
  }
  return null
}

export function ApprovalCard({ approval, onDecided }: Props) {
  const [current, setCurrent] = useState<PendingApproval>(approval)
  const [editing, setEditing] = useState(false)
  const decide = useDecide(onDecided)
  const edit = useEditApproval((fresh) => {
    setCurrent(fresh)
    setEditing(false)
  })
  const decided = decide.data
  const error = describeDecisionError(decide.error ?? edit.error)
  const editable = mailFields(current) ?? eventFields(current)
  const busy = decide.isPending || edit.isPending

  return (
    <Card
      size="sm"
      id={`approval-${current.id}`}
      className="animate-enter"
      data-testid={`approval-${current.id}`}
    >
      <CardContent className="flex flex-col gap-2">
        <p className="text-[9px] font-medium tracking-[0.26em] uppercase text-muted-foreground">
          Approval #{current.id} · {current.action}
        </p>
        {editing && editable ? (
          <ApprovalEditor
            initial={editable}
            saving={edit.isPending}
            onSave={(change) => edit.mutate({ id: current.id, change })}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {current.preview}
          </p>
        )}
        {decided ? (
          <p className="text-sm">
            Status: <span className="font-medium">{decided.status}</span>
            {resultText(decided) && (
              <span className="text-muted-foreground">
                {" "}
                · {resultText(decided)}
              </span>
            )}
          </p>
        ) : (
          !editing && (
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={busy}
                onClick={() =>
                  decide.mutate({ id: current.id, decision: "approve" })
                }
              >
                {primaryLabel(current.action)}
              </Button>
              {editable && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => setEditing(true)}
                >
                  Edit
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  decide.mutate({ id: current.id, decision: "reject" })
                }
              >
                Discard
              </Button>
            </div>
          )
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
