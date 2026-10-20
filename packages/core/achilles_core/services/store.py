from sqlmodel import Session

from achilles_core.db.models import Setting


def read_setting(session: Session, user_id: int, key: str) -> str | None:
    row = session.get(Setting, (user_id, key))
    return row.value if row else None


def write_setting(session: Session, user_id: int, key: str, value: str) -> None:
    row = session.get(Setting, (user_id, key))
    if row is None:
        row = Setting(user_id=user_id, key=key, value=value)
    else:
        row.value = value
    session.add(row)
    session.commit()
