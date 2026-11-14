import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { getJson, postJson } from "@/lib/api"
import { liveQuery } from "@/lib/live"
import type { Approval } from "@/features/approvals/types"
import { todayKey } from "@/features/today/useToday"
import type {
  ComposeDraft,
  Folder,
  FollowUp,
  LabelChange,
  RefreshResult,
  ReplyMode,
  Thread,
  ThreadPage,
} from "./types"

export const mailKey = ["mail"]
const PAGE_SIZE = 20

export function useFolders() {
  return useQuery({
    queryKey: [...mailKey, "folders"],
    queryFn: () => getJson<Folder[]>("/api/mail/folders"),
    ...liveQuery,
  })
}

function threadsUrl(folder: string, query: string, pageToken: string) {
  const params = new URLSearchParams({ folder, size: String(PAGE_SIZE) })
  if (query) params.set("q", query)
  if (pageToken) params.set("page_token", pageToken)
  return `/api/mail/threads?${params}`
}

export function useThreads(folder: string, query: string) {
  return useInfiniteQuery({
    queryKey: [...mailKey, "threads", folder, query],
    queryFn: ({ pageParam }) =>
      getJson<ThreadPage>(threadsUrl(folder, query, pageParam)),
    initialPageParam: "",
    getNextPageParam: (page) => page.next_page_token ?? undefined,
    ...liveQuery,
  })
}

export function useThread(id: string | null, images: boolean) {
  return useQuery({
    queryKey: [...mailKey, "thread", id, images],
    queryFn: () =>
      getJson<Thread>(`/api/mail/threads/${id}${images ? "?images=true" : ""}`),
    enabled: id !== null,
    refetchOnWindowFocus: true,
  })
}

export function useMailRefresh() {
  const queryClient = useQueryClient()
  return async () => {
    await queryClient.invalidateQueries({ queryKey: mailKey })
    await queryClient.invalidateQueries({ queryKey: todayKey })
  }
}

export function useLabelChange() {
  const refresh = useMailRefresh()
  return useMutation({
    mutationFn: ({ threadId, add = [], remove = [] }: LabelChange) =>
      postJson<{ id: string; labels: string[] }>(
        `/api/mail/threads/${threadId}/labels`,
        { add, remove },
      ),
    onSuccess: refresh,
  })
}

export function useReplyDraft(threadId: string) {
  return useMutation({
    mutationFn: (mode: ReplyMode) =>
      getJson<ComposeDraft>(`/api/mail/threads/${threadId}/reply?mode=${mode}`),
  })
}

export function useCompose() {
  return useMutation({
    mutationFn: (draft: ComposeDraft) =>
      postJson<Approval>("/api/mail/compose", draft),
  })
}

type WriteArgs = { instruction: string; thread_id: string | null; to: string }

export function useWriteWithHomer() {
  return useMutation({
    mutationFn: (args: WriteArgs) =>
      postJson<{ body: string }>("/api/mail/write", args),
  })
}

export function useLabelInbox() {
  const refresh = useMailRefresh()
  return useMutation({
    mutationFn: () => postJson<RefreshResult>("/api/inbox/refresh", {}),
    onSuccess: refresh,
  })
}

export function useFollowUp(messageId: string) {
  return useMutation({
    mutationFn: () =>
      postJson<FollowUp>(`/api/inbox/${messageId}/follow-up`, {}),
  })
}
