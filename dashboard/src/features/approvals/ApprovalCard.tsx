import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { describeDecisionError, useDecide } from "./useDecide"
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
  const decide = useDecide(onDecided)
  const decided = decide.data
  const error = describeDecisionError(decide.error)

  return (
    <Card size="sm" data-testid={`approval-${approval.id}`}>
      <CardContent className="flex flex-col gap-2">
        <p className="text-xs text-muted-foreground">
          Approval #{approval.id} · {approval.action}
        </p>
        <p className="text-sm whitespace-pre-wrap">{approval.preview}</p>
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
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate({ id: approval.id, decision: "approve" })
              }
            >
              Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate({ id: approval.id, decision: "reject" })
              }
            >
              Reject
            </Button>
          </div>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
