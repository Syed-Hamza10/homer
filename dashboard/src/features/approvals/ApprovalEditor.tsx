import { useState } from "react"
import { Button } from "@/components/ui/button"
import { EventForm } from "./EventForm"
import { MailForm } from "./MailForm"
import type { ApprovalEdit } from "./types"

type Props = {
  initial: ApprovalEdit
  saving: boolean
  onSave: (change: ApprovalEdit) => void
  onCancel: () => void
}

export function ApprovalEditor({ initial, saving, onSave, onCancel }: Props) {
  const [value, setValue] = useState<ApprovalEdit>(initial)

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        onSave(value)
      }}
    >
      {"to" in value ? (
        <MailForm value={value} onChange={setValue} />
      ) : (
        <EventForm value={value} onChange={setValue} />
      )}
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={saving}>
          Save
        </Button>
        <Button size="sm" type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
