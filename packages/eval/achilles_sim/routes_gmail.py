from typing import Any

from fastapi import APIRouter

from achilles_sim.deps import Authed, Sim
from achilles_sim.errors import ApiError

router = APIRouter(prefix="/gmail/v1/users/me", dependencies=[Authed])


@router.get("/profile")
def profile(sim: Sim) -> dict[str, Any]:
    box = sim.mailbox
    threads = {m["threadId"] for m in box.messages.values()}
    return {
        "emailAddress": box.owner,
        "messagesTotal": len(box.messages),
        "threadsTotal": len(threads),
        "historyId": str(box.history_id),
    }


@router.get("/messages")
def list_messages(
    sim: Sim, q: str = "", maxResults: int = 100, pageToken: str = "0"
) -> dict[str, Any]:
    found = sim.mailbox.search(q, sim.now)
    offset = int(pageToken)
    page = found[offset : offset + maxResults]
    response: dict[str, Any] = {
        "messages": [{"id": m["id"], "threadId": m["threadId"]} for m in page],
        "resultSizeEstimate": len(found),
    }
    if offset + maxResults < len(found):
        response["nextPageToken"] = str(offset + maxResults)
    return response


@router.post("/messages")
def insert_message(
    sim: Sim, body: dict[str, Any], internalDateSource: str = "receivedTime"
) -> dict[str, Any]:
    if "raw" not in body:
        raise ApiError(400, "Missing raw message.")
    message = sim.mailbox.insert(
        body["raw"],
        body.get("labelIds", []),
        body.get("threadId"),
        sim.now,
        internalDateSource == "dateHeader",
    )
    return sim.mailbox.render(message, "minimal")


@router.get("/messages/{message_id}")
def get_message(sim: Sim, message_id: str, format: str = "full") -> dict[str, Any]:
    return sim.mailbox.render(sim.mailbox.get(message_id), format)


@router.post("/messages/{message_id}/modify")
def modify_message(sim: Sim, message_id: str, body: dict[str, Any]) -> dict[str, Any]:
    message = sim.mailbox.modify(
        message_id, body.get("addLabelIds", []), body.get("removeLabelIds", [])
    )
    return sim.mailbox.render(message, "minimal")


@router.post("/messages/{message_id}/trash")
def trash_message(sim: Sim, message_id: str) -> dict[str, Any]:
    return sim.mailbox.render(sim.mailbox.trash(message_id), "minimal")


@router.get("/threads/{thread_id}")
def get_thread(sim: Sim, thread_id: str, format: str = "full") -> dict[str, Any]:
    messages = sim.mailbox.thread(thread_id)
    return {
        "id": thread_id,
        "historyId": messages[-1]["historyId"],
        "messages": [sim.mailbox.render(m, format) for m in messages],
    }


@router.get("/labels")
def list_labels(sim: Sim) -> dict[str, Any]:
    return {"labels": list(sim.mailbox.labels.values())}


@router.post("/labels")
def create_label(sim: Sim, body: dict[str, Any]) -> dict[str, Any]:
    if not body.get("name"):
        raise ApiError(400, "Label name is required.")
    return sim.mailbox.create_label(body["name"])


@router.post("/drafts")
def create_draft(sim: Sim, body: dict[str, Any]) -> dict[str, Any]:
    message = body.get("message", {})
    if "raw" not in message:
        raise ApiError(400, "Missing raw message.")
    return sim.mailbox.create_draft(message["raw"], message.get("threadId"), sim.now)


@router.get("/drafts/{draft_id}")
def get_draft(sim: Sim, draft_id: str) -> dict[str, Any]:
    return sim.mailbox.draft(draft_id)


@router.post("/drafts/send")
def send_draft(sim: Sim, body: dict[str, Any]) -> dict[str, Any]:
    if body.get("id") not in sim.mailbox.drafts:
        raise ApiError(404, "Requested entity was not found.")
    return sim.mailbox.send_draft(body["id"], sim.now)


@router.get("/history")
def list_history(sim: Sim, startHistoryId: str, maxResults: int = 100) -> dict[str, Any]:
    if int(startHistoryId) > sim.mailbox.history_id:
        raise ApiError(404, "Requested entity was not found.")
    records = sim.mailbox.history_since(startHistoryId)[:maxResults]
    response: dict[str, Any] = {"historyId": str(sim.mailbox.history_id)}
    if records:
        response["history"] = records
    return response
