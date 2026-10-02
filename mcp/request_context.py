from contextvars import ContextVar

current_user: ContextVar[str | None] = ContextVar("current_user", default=None)