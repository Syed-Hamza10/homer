from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model

from homer_core.agent.prompt import known_name
from homer_core.db.models import User
from homer_core.mcp.manager import McpManager
from homer_core.services.errors import DomainError, NotFound
from homer_core.services.followups import clean_subject
from homer_core.services.inbox import clean, sender_email
from homer_core.services.rules import ClientRules

PROMPT = """Write a reply to the email below.
Match this tone: {tone}.
Sign off with this signature: {signature}.
Return only the reply body, with no subject line and no commentary.

From: {sender}
Subject: {subject}

{body}
"""


async def draft_reply(
    user: User,
    manager: McpManager,
    model: Model,
    rules: ClientRules,
    message_id: str,
) -> dict[str, Any]:
    message = await manager.call("google", "mail_get", {"message_id": message_id})
    if not isinstance(message, dict) or not message.get("id"):
        raise NotFound(f"message {message_id} not found")
    sender = message.get("from", "")
    subject = message.get("subject", "")
    body = clean(message.get("body", ""))
    prompt = PROMPT.format(
        tone=rules.tone,
        signature=rules.signature or known_name(user.name) or "a short sign-off with no name",
        sender=sender,
        subject=subject,
        body=body,
    )
    result = await Agent(model, output_type=str).run(prompt)
    reply = result.output.strip()
    if not reply:
        raise DomainError("the model returned an empty draft")
    draft = await manager.call(
        "google",
        "mail_draft",
        {
            "to": sender_email(sender),
            "subject": f"Re: {clean_subject(subject)}",
            "body": reply,
            "thread_id": message.get("thread_id"),
        },
    )
    return {
        "draft_id": draft.get("draft_id"),
        "to": sender_email(sender),
        "subject": f"Re: {clean_subject(subject)}",
        "body": reply,
    }
