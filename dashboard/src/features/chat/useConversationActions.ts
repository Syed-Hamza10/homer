import { useMutation, useQueryClient } from "@tanstack/react-query"
import { del, patchJson } from "@/lib/api"
import type { Conversation } from "./types"
import { conversationsKey } from "./useConversations"

type Rename = { id: number; title: string }

export function useConversationActions() {
  const queryClient = useQueryClient()
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: conversationsKey })
  const rename = useMutation({
    mutationFn: ({ id, title }: Rename) =>
      patchJson<Conversation>(`/api/conversations/${id}`, { title }),
    onSuccess: refresh,
  })
  const remove = useMutation({
    mutationFn: (id: number) => del(`/api/conversations/${id}`),
    onSuccess: refresh,
  })
  return { rename, remove }
}
