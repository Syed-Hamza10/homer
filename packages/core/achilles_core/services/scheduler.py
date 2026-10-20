from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import Engine, update
from sqlmodel import Session

from achilles_core.agent.runtime import Runtime
from achilles_core.config import Settings
from achilles_core.db.models import Reminder, User
from achilles_core.mcp.manager import ExecuteFailed, ServerUnavailable
from achilles_core.services import briefs, followups
from achilles_core.services.calendar import refresh_calendar
from achilles_core.services.inbox import label_rows, upsert_email
from achilles_core.services.rules import get_rules
from achilles_core.services.store import read_setting, write_setting
from achilles_core.services.users import first_user

log = structlog.get_logger(__name__)

CURSOR_KEY = "gmail_cursor"
CHANGED_LIMIT = 50


class Scheduler:
    def __init__(self, settings: Settings, engine: Engine, runtime: Runtime) -> None:
        self.settings = settings
        self.engine = engine
        self.runtime = runtime
        self.inner: AsyncIOScheduler | None = None

    def start(self) -> None:
        if not self.settings.scheduler_enabled:
            return
        with Session(self.engine) as session:
            user = first_user(session)
        timezone = ZoneInfo(user.timezone if user else self.settings.timezone)
        inner = AsyncIOScheduler(timezone=timezone)
        jobs = (
            (self.poll_mail, "interval", {"minutes": 3}, "poll_mail"),
            (self.poll_calendar, "interval", {"minutes": 10}, "poll_calendar"),
            (self.check_reminders, "interval", {"minutes": 1}, "reminders"),
            (self.check_followups, "interval", {"minutes": 10}, "follow_ups"),
            (
                self.morning_brief,
                CronTrigger(hour=7, minute=30, timezone=timezone),
                {},
                "morning_brief",
            ),
            (
                self.eod_digest,
                CronTrigger(hour=18, minute=0, timezone=timezone),
                {},
                "eod_digest",
            ),
        )
        for job, trigger, options, job_id in jobs:
            inner.add_job(
                self.guard(job),
                trigger,
                id=job_id,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
                **options,
            )
        inner.start()
        self.inner = inner
        log.info("scheduler_started", timezone=str(timezone))

    def stop(self) -> None:
        if self.inner is not None:
            self.inner.shutdown(wait=False)
            self.inner = None

    def guard(self, job):
        async def run() -> None:
            try:
                await job()
            except Exception:
                log.exception("scheduler_job_failed", job=job.__name__)

        return run

    def _user(self, session: Session) -> User | None:
        return first_user(session)

    async def poll_mail(self) -> None:
        with Session(self.engine) as session:
            user = self._user(session)
            if user is None:
                return
            rules = get_rules(session, user.id)
            cursor = read_setting(session, user.id, CURSOR_KEY)
            args = {"cursor": cursor} if cursor else {}
            try:
                result = await self.runtime.manager.call("google", "mail_changes_since", args)
            except (ExecuteFailed, ServerUnavailable):
                log.exception("mail_poll_failed")
                return
            if not isinstance(result, dict) or "cursor" not in result:
                if isinstance(result, dict) and result.get("error"):
                    write_setting(session, user.id, CURSOR_KEY, "")
                return
            write_setting(session, user.id, CURSOR_KEY, str(result["cursor"]))
            changed = []
            for message_id in result.get("changed_ids", [])[:CHANGED_LIMIT]:
                try:
                    message = await self.runtime.manager.call(
                        "google", "mail_get", {"message_id": message_id}
                    )
                except (ExecuteFailed, ServerUnavailable):
                    continue
                if isinstance(message, dict) and message.get("id"):
                    changed.append(
                        upsert_email(session, user.id, message, rules, datetime.now(UTC))
                    )
            if changed:
                await label_rows(self.runtime.manager, changed)

    async def poll_calendar(self) -> None:
        with Session(self.engine) as session:
            user = self._user(session)
            if user is not None:
                await refresh_calendar(session, user, self.runtime.manager, days=14)

    async def check_reminders(self) -> None:
        with Session(self.engine) as session:
            user = self._user(session)
            if user is None:
                return
            session.exec(
                update(Reminder)
                .where(
                    Reminder.user_id == user.id,
                    Reminder.status == "pending",
                    Reminder.due_at <= datetime.now(UTC),
                )
                .values(status="due")
            )
            session.commit()

    async def check_followups(self) -> None:
        with Session(self.engine) as session:
            user = self._user(session)
            if user is None:
                return
            rules = get_rules(session, user.id)
            await followups.check_followups(
                session, user, self.runtime.manager, rules, datetime.now(UTC)
            )

    async def morning_brief(self) -> None:
        with Session(self.engine) as session:
            user = self._user(session)
            if user is None:
                return
            rules = get_rules(session, user.id)
            await briefs.morning_brief(
                session, user, self.runtime.manager, rules, datetime.now(UTC)
            )

    async def eod_digest(self) -> None:
        with Session(self.engine) as session:
            user = self._user(session)
            if user is None:
                return
            rules = get_rules(session, user.id)
            await briefs.eod_digest(session, user, self.runtime.manager, rules, datetime.now(UTC))


def build_scheduler(settings: Settings, engine: Engine, runtime: Runtime) -> Scheduler:
    return Scheduler(settings, engine, runtime)
