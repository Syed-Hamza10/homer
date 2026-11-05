import { ApprovalCard } from "@/features/approvals/ApprovalCard"
import type { Approval } from "@/features/approvals/types"
import { PanelFrame } from "./PanelFrame"

type Props = {
  approval: Approval
  onClose: () => void
  onDecided: () => void
}

export function ApprovalPanel({ approval, onClose, onDecided }: Props) {
  return (
    <PanelFrame
      eyebrow="Needs your approval"
      testId="calendar-approval"
      onClose={onClose}
    >
      <p className="text-xs text-muted-foreground">
        Nothing changes in your calendar until you approve.
      </p>
      <ApprovalCard
        key={approval.id}
        approval={approval}
        onDecided={onDecided}
      />
    </PanelFrame>
  )
}
