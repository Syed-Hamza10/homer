export type Conversation = { id: number; title: string; updated_at: string }

export type Message = {
  id: number
  role: "user" | "assistant"
  content: string
  stopped?: boolean
  created_approval?: boolean
  created_at: string
  choice?: ChoiceEvent | null
}

export type MetaEvent = { conversation_id: number; message_id: number }
export type TokenEvent = { text: string }
export type ReplaceEvent = { text: string }
export type StatusEvent = { text: string }
export type DoneEvent = { input_tokens: number; output_tokens: number }
export type ErrorEvent = { message: string }
export type ToolCallEvent = { name: string; args: Record<string, unknown> }
export type ToolResultEvent = { name: string; summary: string }
export type ApprovalRequiredEvent = {
  approval_id: number
  action: string
  preview: string
  payload: Record<string, unknown>
}

export type GoogleReconnectEvent = { url: string }

export type ChoiceOption = { id: string; label: string; detail: string }
export type ChoiceEvent = {
  question_id: string
  prompt: string
  options: ChoiceOption[]
  allow_other: boolean
  answered?: string | null
}
export type ChoiceHint = { question_id: string; option_id: string }

export type ActivityItem =
  | ({ kind: "tool_call" } & ToolCallEvent)
  | ({ kind: "tool_result" } & ToolResultEvent)
  | ({ kind: "approval" } & ApprovalRequiredEvent)
  | ({ kind: "reconnect" } & GoogleReconnectEvent)
  | ({ kind: "choice" } & ChoiceEvent)
