from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import Engine, update
from sqlmodel import Session

from homer_core.agent.runtime import Runtime
from homer_core.config import Settings
from homer_core.db.models import Reminder, User
from homer_core.mcp.manager import ExecuteFailed, ServerUnavailable
from homer_core.services import backup as backup_service
from homer_core.services import briefs, followups, models
from homer_core.services import health as health_service
from homer_core.services.calendar import refresh_calendar
from homer_core.services.inbox import label_rows, normalise, upsert_email
from homer_core.services.rules import ClientRules, get_rules
from homer_core.services.store import read_setting, write_setting
from homer_core.services.users import first_user
from homer_net import AllowlistedClient

log = structlog.get_logger(__name__)

CURSOR_KEY = "gmail_cursor"
CHANGED_LIMIT = 50
BACKFILL_QUERY = "newer_than:2d"
DEFAULT_GRACE = 3600
DAY = 24 * 3600


def rest_of_day(hour: int, minute: int) -> int:
    """Grace for a daily job: a brief missed while the laptop slept runs on wake that day only."""
    return DAY - hour * 3600 - minute * 60


def daily(hour: int, minute: int, timezone: ZoneInfo) -> CronTrigger:
    return CronTrigger(hour=hour, minute=minute, timezone=timezone)


class Scheduler:
    def __init__(
        self, settings: Settings, engine: Engine, runtime: Runtime, client: AllowlistedClient
    ) -> None:
        self.settings = settings
        self.engine = engine
        self.runtime = runtime
        self.client = client
        self.inner: AsyncIOScheduler | None = None
        self.health: health_service.HealthReport | None = None

    def start(self) -> None:
        if not self.settings.scheduler_enabled:
            return
        with Session(self.engine) as session:
            user = first_user(session)
        timezone = ZoneInfo(user.timezone if user else self.settings.timezone)
        inner = AsyncIOScheduler(timezone=timezone)
        jobs = (
            (self.poll_mail, "interval", {"minutes": 3}, DEFAULT_GRACE),
            (self.poll_calendar, "interval", {"minutes": 10}, DEFAULT_GRACE),
            (self.check_reminders, "interval", {"minutes": 1}, DEFAULT_GRACE),
            (self.check_followups, "interval", {"minutes": 10}, DEFAULT_GRACE),
            (
                self.health_check,
                "interval",
                {"minutes": 10, "next_run_time": datetime.now(timezone)},
                DEFAULT_GRACE,
            ),
            (self.warm_up, daily(6, 45, timezone), {}, DEFAULT_GRACE),
            (self.morning_brief, daily(7, 30, timezone), {}, rest_of_day(7, 30)),
            (self.eod_digest, daily(18, 0, timezone), {}, rest_of_day(18, 0)),
            (self.backup, daily(3, 0, timezone), {}, DEFAULT_GRACE),
        )
        for job, trigger, options, grace in jobs:
            inner.add_job(
                self.guard(job),
                trigger,
                id=job.__name__,
                misfire_grace_time=grace,
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
            if result.get("stale"):
                log.warning("mail_cursor_stale")
                await self.backfill_mail(session, user, rules)
                return
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

    async def backfill_mail(self, session: Session, user: User, rules: ClientRules) -> None:
        try:
            result = await self.runtime.manager.call(
                "google", "mail_search", {"query": BACKFILL_QUERY, "max_results": CHANGED_LIMIT}
            )
        except (ExecuteFailed, ServerUnavailable):
            log.exception("mail_backfill_failed")
            return
        now = datetime.now(UTC)
        rows = [
            upsert_email(session, user.id, message, rules, now)
            for message in normalise(result)
            if message.get("id")
        ]
        if rows:
            await label_rows(self.runtime.manager, rows)

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

    async def health_check(self) -> None:
        with Session(self.engine) as session:
            user = self._user(session)
            rules = get_rules(session, user.id) if user else ClientRules()
        report = await health_service.check(
            self.settings,
            self.client,
            self.runtime.model.model_name,
            self.runtime.manager,
            rules,
        )
        self.health = report
        if report.problems:
            log.warning("health_check_problems", problems=report.problems)

    async def warm_up(self) -> None:
        result = await models.smoke(self.runtime.model)
        log.info("model_warmed", ok=result.ok, latency_ms=result.latency_ms, error=result.error)

    async def backup(self) -> None:
        path = backup_service.create_backup(self.settings.homer_home)
        log.info("backup_created", path=str(path))


def build_scheduler(
    settings: Settings, engine: Engine, runtime: Runtime, client: AllowlistedClient
) -> Scheduler:
    return Scheduler(settings, engine, runtime, client)
