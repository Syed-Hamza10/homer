export type Conversation = { id: string; title: string; updated_at: string }

export type Message = {
  id: string
  role: "user" | "assistant"
  content: string
  created_at: string
}

export type MetaEvent = { conversation_id: string; message_id: string }
export type TokenEvent = { text: string }
export type ReplaceEvent = { text: string }
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

export type ActivityItem =
  | ({ kind: "tool_call" } & ToolCallEvent)
  | ({ kind: "tool_result" } & ToolResultEvent)
  | ({ kind: "approval" } & ApprovalRequiredEvent)
