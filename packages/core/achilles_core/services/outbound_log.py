from sqlalchemy import Engine
from sqlmodel import Session

from achilles_core.db.models import OutboundLog
from achilles_net import OutboundCall
from achilles_net.client import LogFn


def make_logger(engine: Engine) -> LogFn:
    def log(call: OutboundCall) -> None:
        with Session(engine) as session:
            session.add(
                OutboundLog(
                    method=call.method,
                    host=call.host,
                    path=call.path,
                    status=call.status,
                    duration_ms=call.duration_ms,
                )
            )
            session.commit()

    return log
