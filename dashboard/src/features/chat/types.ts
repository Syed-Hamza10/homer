export type Conversation = { id: string; title: string; updated_at: string }

export type Message = {
  id: string
  role: "user" | "assistant"
  content: string
  created_at: string
}

export type MetaEvent = { conversation_id: string; message_id: string }
export type TokenEvent = { text: string }
export type DoneEvent = { input_tokens: number; output_tokens: number }
export type ErrorEvent = { message: string }
