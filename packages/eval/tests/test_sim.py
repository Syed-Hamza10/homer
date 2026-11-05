import base64
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient

from homer_sim.app import create_app
from homer_sim.state import KNOWN_TOKEN

AUTH = {"Authorization": f"Bearer {KNOWN_TOKEN}"}
GMAIL = "/gmail/v1/users/me"
CAL = "/calendar/v3/calendars/primary/events"
KICKOFF_THREAD = "dbe626c57687283a"
KICKOFF_MESSAGES = ["5995acc9cb4b7eee", "c1c5afb09a9eb792", "518115189b45f53b"]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        yield client


def raw_draft(to: str, subject: str, body: str) -> str:
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")


def test_requires_bearer(client: TestClient) -> None:
    response = client.get(f"{GMAIL}/messages")
    assert response.status_code == 401
    assert response.json()["error"]["status"] == "UNAUTHENTICATED"
    assert (
        client.get(f"{GMAIL}/messages", headers={"Authorization": "Bearer nope"}).status_code == 401
    )


def test_seed_counts(client: TestClient) -> None:
    counts = client.get("/_sim/state").json()
    assert counts["messages"] == 12
    assert counts["events"] == 6
    assert counts["contacts"] == 7


def test_search_and_full_message(client: TestClient) -> None:
    listing = client.get(f"{GMAIL}/messages", params={"q": "from:maya is:unread"}, headers=AUTH)
    ids = [m["id"] for m in listing.json()["messages"]]
    assert ids == [KICKOFF_MESSAGES[2]]
    full = client.get(
        f"{GMAIL}/messages/{KICKOFF_MESSAGES[2]}", params={"format": "full"}, headers=AUTH
    ).json()
    headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
    assert headers["Subject"].startswith("Re: Kickoff")
    assert full["payload"]["mimeType"] == "text/html"
    assert "data" in full["payload"]["body"]
    meta = client.get(
        f"{GMAIL}/messages/{KICKOFF_MESSAGES[2]}", params={"format": "metadata"}, headers=AUTH
    )
    assert "body" not in meta.json()["payload"]


def test_search_by_date_and_category(client: TestClient) -> None:
    def ids(query: str) -> list[str]:
        listing = client.get(f"{GMAIL}/messages", params={"q": query}, headers=AUTH).json()
        return [m["id"] for m in listing.get("messages", [])]

    everything = ids("")
    future = int((datetime.now(UTC) + timedelta(days=1)).timestamp())
    assert ids(f"after:{future}") == [] and ids(f"before:{future}") == everything
    assert ids("after:2000/01/01") == everything
    assert ids("-category:promotions") == everything and ids("category:promotions") == []
    message = EmailMessage()
    message["From"] = "news@example.test"
    message["List-Unsubscribe"] = "<mailto:unsubscribe@example.test>"
    message.set_content("Weekly news")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {"raw": raw, "labelIds": ["INBOX", "CATEGORY_PROMOTIONS"]}
    inserted = client.post(f"{GMAIL}/messages", json=body, headers=AUTH).json()
    assert ids("category:promotions") == [inserted["id"]]
    full = client.get(f"{GMAIL}/messages/{inserted['id']}", headers=AUTH).json()
    names = {h["name"] for h in full["payload"]["headers"]}
    assert "List-Unsubscribe" in names


def test_pagination(client: TestClient) -> None:
    first = client.get(f"{GMAIL}/messages", params={"maxResults": 5}, headers=AUTH).json()
    assert len(first["messages"]) == 5 and first["nextPageToken"] == "5"
    last = client.get(
        f"{GMAIL}/messages", params={"maxResults": 5, "pageToken": "10"}, headers=AUTH
    ).json()
    assert len(last["messages"]) == 2 and "nextPageToken" not in last


def test_thread_and_modify(client: TestClient) -> None:
    thread = client.get(f"{GMAIL}/threads/{KICKOFF_THREAD}", headers=AUTH).json()
    assert [m["id"] for m in thread["messages"]] == KICKOFF_MESSAGES
    modified = client.post(
        f"{GMAIL}/messages/{KICKOFF_MESSAGES[2]}/modify",
        json={"removeLabelIds": ["INBOX", "UNREAD"], "addLabelIds": ["Label_3"]},
        headers=AUTH,
    ).json()
    assert "INBOX" not in modified["labelIds"] and "Label_3" in modified["labelIds"]


def test_labels(client: TestClient) -> None:
    names = {
        label["name"] for label in client.get(f"{GMAIL}/labels", headers=AUTH).json()["labels"]
    }
    assert {"INBOX", "Clients", "Invoices", "Follow up"} <= names
    created = client.post(f"{GMAIL}/labels", json={"name": "Urgent"}, headers=AUTH).json()
    assert created["type"] == "user" and created["id"].startswith("Label_")


def test_draft_send_and_history(client: TestClient) -> None:
    start = client.get(f"{GMAIL}/profile", headers=AUTH).json()["historyId"]
    raw = raw_draft("maya.lindqvist@example.test", "Re: Kickoff", "Thursday 14:00 works.")
    draft = client.post(
        f"{GMAIL}/drafts", json={"message": {"raw": raw, "threadId": KICKOFF_THREAD}}, headers=AUTH
    ).json()
    assert draft["message"]["labelIds"] == ["DRAFT"]
    assert client.get("/_sim/state").json()["drafts"] == 1
    sent = client.post(f"{GMAIL}/drafts/send", json={"id": draft["id"]}, headers=AUTH).json()
    assert sent["labelIds"] == ["SENT"] and sent["threadId"] == KICKOFF_THREAD
    counts = client.get("/_sim/state").json()
    assert counts["drafts"] == 0 and counts["sent"] == 4
    history = client.get(f"{GMAIL}/history", params={"startHistoryId": start}, headers=AUTH).json()
    added = [m["message"]["id"] for h in history["history"] for m in h.get("messagesAdded", [])]
    assert sent["id"] in added
    assert int(history["historyId"]) > int(start)
    empty = client.get(
        f"{GMAIL}/history", params={"startHistoryId": history["historyId"]}, headers=AUTH
    ).json()
    assert "history" not in empty


def test_generated_ids_have_gmail_shapes(client: TestClient) -> None:
    raw = raw_draft("maya.lindqvist@example.test", "Shapes", "x")
    draft = client.post(f"{GMAIL}/drafts", json={"message": {"raw": raw}}, headers=AUTH).json()
    assert re.fullmatch(r"r-\d{19}", draft["id"])
    assert re.fullmatch(r"[0-9a-f]{16}", draft["message"]["id"])
    assert re.fullmatch(r"[0-9a-f]{16}", draft["message"]["threadId"])
    label = client.post(f"{GMAIL}/labels", json={"name": "Shapes"}, headers=AUTH).json()
    assert label["id"] == "Label_4"
    history = [int(client.get(f"{GMAIL}/profile", headers=AUTH).json()["historyId"])]
    client.post(f"{GMAIL}/drafts/send", json={"id": draft["id"]}, headers=AUTH).raise_for_status()
    history.append(int(client.get(f"{GMAIL}/profile", headers=AUTH).json()["historyId"]))
    assert history[1] > history[0]


def test_drafts_list_newest_first(client: TestClient) -> None:
    assert client.get(f"{GMAIL}/drafts", headers=AUTH).json() == {"resultSizeEstimate": 0}
    first = client.post(
        f"{GMAIL}/drafts",
        json={"message": {"raw": raw_draft("a@example.test", "One", "x")}},
        headers=AUTH,
    ).json()
    second = client.post(
        f"{GMAIL}/drafts",
        json={"message": {"raw": raw_draft("b@example.test", "Two", "y")}},
        headers=AUTH,
    ).json()
    listing = client.get(f"{GMAIL}/drafts", params={"maxResults": 1}, headers=AUTH).json()
    assert [d["id"] for d in listing["drafts"]] == [second["id"]]
    assert "payload" not in listing["drafts"][0]["message"]
    meta = client.get(f"{GMAIL}/drafts/{first['id']}", params={"format": "metadata"}, headers=AUTH)
    assert "body" not in meta.json()["message"]["payload"]
    assert client.get(f"{GMAIL}/drafts/nope", headers=AUTH).status_code == 404


def test_expired_history_returns_404_for_old_cursors(client: TestClient) -> None:
    old = client.get(f"{GMAIL}/profile", headers=AUTH).json()["historyId"]
    client.post(
        f"{GMAIL}/messages/{KICKOFF_MESSAGES[0]}/modify",
        json={"addLabelIds": ["INBOX"]},
        headers=AUTH,
    )
    before = client.get(f"{GMAIL}/history", params={"startHistoryId": old}, headers=AUTH)
    assert before.status_code == 200 and before.json()["history"]

    client.post("/_sim/expire-history")
    stale = client.get(f"{GMAIL}/history", params={"startHistoryId": old}, headers=AUTH)
    assert stale.status_code == 404
    fresh = client.get(f"{GMAIL}/profile", headers=AUTH).json()["historyId"]
    current = client.get(f"{GMAIL}/history", params={"startHistoryId": fresh}, headers=AUTH)
    assert current.status_code == 200 and "history" not in current.json()


def test_calendar_crud_and_free_busy(client: TestClient) -> None:
    now = datetime.now(UTC)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    window = {"timeMin": monday.isoformat(), "timeMax": (monday + timedelta(days=7)).isoformat()}
    items = client.get(CAL, params={**window, "orderBy": "startTime"}, headers=AUTH).json()["items"]
    assert len(items) == 6 and items[0]["summary"] == "Weekly planning"
    start = monday + timedelta(days=5, hours=10)
    created = client.post(
        CAL,
        json={
            "summary": "Kickoff",
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
            "attendees": [{"email": "maya.lindqvist@example.test"}],
        },
        headers=AUTH,
    ).json()
    assert created["status"] == "confirmed" and created["attendees"][0]["responseStatus"]
    patched = client.patch(f"{CAL}/{created['id']}", json={"summary": "Kickoff v2"}, headers=AUTH)
    assert patched.json()["summary"] == "Kickoff v2"
    busy = client.post(
        "/calendar/v3/freeBusy", json={**window, "items": [{"id": "primary"}]}, headers=AUTH
    ).json()["calendars"]["primary"]["busy"]
    assert len(busy) == 7
    assert client.delete(f"{CAL}/{created['id']}", headers=AUTH).status_code == 204
    assert client.get(f"{CAL}/{created['id']}", headers=AUTH).json()["status"] == "cancelled"
    assert len(client.get(CAL, params=window, headers=AUTH).json()["items"]) == 6
    assert client.get(f"{CAL}/missing", headers=AUTH).status_code == 404


def test_contacts(client: TestClient) -> None:
    found = client.get(
        "/v1/people:searchContacts",
        params={"query": "maya", "readMask": "names,emailAddresses"},
        headers=AUTH,
    ).json()
    assert found["results"][0]["person"]["emailAddresses"][0]["value"] == (
        "maya.lindqvist@example.test"
    )
    assert (
        client.get("/v1/people:searchContacts", params={"query": "zzz"}, headers=AUTH).json() == {}
    )


def test_token_and_reset(client: TestClient) -> None:
    issued = client.post("/token", data={"grant_type": "refresh_token", "refresh_token": "r"})
    token = issued.json()
    assert token["token_type"] == "Bearer" and token["expires_in"] > 0
    assert (
        client.get(
            f"{GMAIL}/labels", headers={"Authorization": f"Bearer {token['access_token']}"}
        ).status_code
        == 200
    )
    assert client.post("/token", data={"grant_type": "password"}).status_code == 400
    client.post(f"{GMAIL}/labels", json={"name": "Temp"}, headers=AUTH)
    assert client.post("/_sim/reset").json()["labels"] == 14


def test_insert_and_trash(client: TestClient) -> None:
    message = EmailMessage()
    message["From"] = "Someone <someone@example.test>"
    message["To"] = "jordan.reyes@example.test"
    message["Subject"] = "Inserted"
    message["Date"] = "Mon, 05 Oct 2026 09:00:00 +0000"
    message.set_content("Hello")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
    inserted = client.post(
        f"{GMAIL}/messages",
        params={"internalDateSource": "dateHeader"},
        json={"raw": raw, "labelIds": ["INBOX", "UNREAD"]},
        headers=AUTH,
    ).json()
    assert inserted["labelIds"] == ["INBOX", "UNREAD"]
    assert inserted["internalDate"] == str(
        int(datetime(2026, 10, 5, 9, tzinfo=UTC).timestamp() * 1000)
    )
    reply = client.post(
        f"{GMAIL}/messages",
        json={"raw": raw, "labelIds": ["SENT"], "threadId": inserted["threadId"]},
        headers=AUTH,
    ).json()
    assert reply["threadId"] == inserted["threadId"]
    assert (
        client.post(
            f"{GMAIL}/messages", json={"raw": raw, "labelIds": ["Nope"]}, headers=AUTH
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{GMAIL}/messages", json={"raw": raw, "threadId": "thr_nope"}, headers=AUTH
        ).status_code
        == 404
    )

    trashed = client.post(f"{GMAIL}/messages/{inserted['id']}/trash", headers=AUTH).json()
    assert trashed["labelIds"] == ["TRASH"]
    found = client.get(
        f"{GMAIL}/messages", params={"q": "subject:Inserted -in:trash"}, headers=AUTH
    )
    assert [m["id"] for m in found.json()["messages"]] == [reply["id"]]


def test_draft_update_keeps_the_id_and_delete_removes_it(client: TestClient) -> None:
    raw = raw_draft("maya.lindqvist@example.test", "Re: Kickoff", "Thursday works.")
    draft = client.post(f"{GMAIL}/drafts", json={"message": {"raw": raw}}, headers=AUTH).json()
    messages = client.get("/_sim/state").json()["messages"]
    new_raw = raw_draft("tomas.keller@example.test", "Changed", "Friday works.")
    updated = client.put(
        f"{GMAIL}/drafts/{draft['id']}", json={"message": {"raw": new_raw}}, headers=AUTH
    ).json()
    assert updated["id"] == draft["id"]
    assert updated["message"]["threadId"] == draft["message"]["threadId"]
    counts = client.get("/_sim/state").json()
    assert counts["drafts"] == 1 and counts["messages"] == messages
    full = client.get(f"{GMAIL}/drafts/{draft['id']}", headers=AUTH).json()
    headers = {h["name"]: h["value"] for h in full["message"]["payload"]["headers"]}
    assert headers["To"] == "tomas.keller@example.test" and headers["Subject"] == "Changed"
    assert client.delete(f"{GMAIL}/drafts/{draft['id']}", headers=AUTH).status_code == 200
    assert client.get("/_sim/state").json()["drafts"] == 0
    assert client.delete(f"{GMAIL}/drafts/{draft['id']}", headers=AUTH).status_code == 404


def test_threads_list_by_label_with_pages(client: TestClient) -> None:
    first = client.get(
        f"{GMAIL}/threads", params={"labelIds": "INBOX", "maxResults": 2}, headers=AUTH
    ).json()
    assert [t["id"] for t in first["threads"]][0] == "f9623318d52f5445"
    assert first["nextPageToken"] == "2" and first["resultSizeEstimate"] == 5
    rest = client.get(
        f"{GMAIL}/threads",
        params={"labelIds": "INBOX", "maxResults": 10, "pageToken": "2"},
        headers=AUTH,
    ).json()
    assert len(rest["threads"]) == 3 and "nextPageToken" not in rest
    starred = client.get(f"{GMAIL}/threads", params={"labelIds": "STARRED"}, headers=AUTH)
    assert starred.json()["threads"] == []


def test_trash_stays_out_of_lists_unless_asked(client: TestClient) -> None:
    client.post(f"{GMAIL}/messages/5cc2f1f78a46377d/trash", headers=AUTH)
    ids = [m["id"] for m in client.get(f"{GMAIL}/messages", headers=AUTH).json()["messages"]]
    assert "5cc2f1f78a46377d" not in ids
    trash = client.get(f"{GMAIL}/messages", params={"labelIds": "TRASH"}, headers=AUTH).json()
    assert [m["id"] for m in trash["messages"]] == ["5cc2f1f78a46377d"]


def test_label_counts_and_thread_modify(client: TestClient) -> None:
    inbox = client.get(f"{GMAIL}/labels/INBOX", headers=AUTH).json()
    assert inbox["threadsTotal"] == 5 and inbox["threadsUnread"] == 4
    modified = client.post(
        f"{GMAIL}/threads/{KICKOFF_THREAD}/modify",
        json={"removeLabelIds": ["UNREAD"], "addLabelIds": ["STARRED"]},
        headers=AUTH,
    ).json()
    assert all("STARRED" in m["labelIds"] for m in modified["messages"])
    after = client.get(f"{GMAIL}/labels/INBOX", headers=AUTH).json()
    assert after["threadsUnread"] == 3
    assert client.get(f"{GMAIL}/labels/Nope", headers=AUTH).status_code == 404


def test_attachments_and_html_snippets(client: TestClient) -> None:
    invoice = client.get(f"{GMAIL}/messages/aed89caf9a7af277", headers=AUTH).json()
    assert invoice["payload"]["mimeType"] == "multipart/mixed"
    assert invoice["payload"]["parts"][1]["filename"] == "invoice-2026-041.pdf"
    meta = client.get(
        f"{GMAIL}/messages/aed89caf9a7af277", params={"format": "metadata"}, headers=AUTH
    ).json()
    assert meta["payload"]["mimeType"] == "multipart/mixed" and "parts" not in meta["payload"]
    proposal = client.get(f"{GMAIL}/messages/81b178b5ebec82bd", headers=AUTH).json()
    assert proposal["snippet"].startswith("Proposal Hi Jordan") and "<" not in proposal["snippet"]


def test_free_busy_per_attendee(client: TestClient) -> None:
    now = datetime.now(UTC)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0)
    span = {"timeMin": monday.isoformat(), "timeMax": (monday + timedelta(days=7)).isoformat()}
    items = [{"id": "primary"}, {"id": "samuel.okafor@example.test"}]
    calendars = client.post(
        "/calendar/v3/freeBusy", json={**span, "items": items}, headers=AUTH
    ).json()["calendars"]
    assert len(calendars["primary"]["busy"]) == 6
    assert len(calendars["samuel.okafor@example.test"]["busy"]) == 1
    call = client.get(f"{CAL}/evt_003", headers=AUTH).json()
    assert call["attendees"][0]["responseStatus"] == "accepted"
    assert client.get(f"{CAL}/evt_002", headers=AUTH).json()["hangoutLink"]


def test_all_day_events(client: TestClient) -> None:
    today = datetime.now(UTC).date()
    body = {
        "summary": "Offsite",
        "start": {"date": today.isoformat()},
        "end": {"date": (today + timedelta(days=1)).isoformat()},
    }
    created = client.post(CAL, json=body, headers=AUTH).json()
    found = client.get(
        CAL,
        params={
            "timeMin": f"{today.isoformat()}T00:00:00Z",
            "timeMax": f"{(today + timedelta(days=1)).isoformat()}T00:00:00Z",
        },
        headers=AUTH,
    ).json()["items"]
    assert created["id"] in [event["id"] for event in found]
