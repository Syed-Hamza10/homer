from sqlalchemy import Engine
from sqlmodel import Session

from homer_core.db.models import OutboundLog
from homer_net import OutboundCall
from homer_net.client import LogFn


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
