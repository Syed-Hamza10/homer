import { useState } from "react"
import { Button } from "@/components/ui/button"
import { eventOrderProblem } from "./editable"
import { EventForm } from "./EventForm"
import { MailForm } from "./MailForm"
import type { ApprovalEdit } from "./types"

type Props = {
  initial: ApprovalEdit
  guests?: boolean
  saving: boolean
  onSave: (change: ApprovalEdit) => void
  onCancel: () => void
}

export function ApprovalEditor({
  initial,
  guests,
  saving,
  onSave,
  onCancel,
}: Props) {
  const [value, setValue] = useState<ApprovalEdit>(initial)
  const invalid = "to" in value ? null : eventOrderProblem(value)

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (!invalid) onSave(value)
      }}
    >
      {"to" in value ? (
        <MailForm value={value} onChange={setValue} />
      ) : (
        <EventForm value={value} onChange={setValue} guests={guests} />
      )}
      {invalid && <p className="text-xs text-destructive">{invalid}</p>}
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={saving || Boolean(invalid)}>
          Save
        </Button>
        <Button size="sm" type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
