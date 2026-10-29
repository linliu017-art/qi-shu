"""Request-scoped identity used by the experimental multi-user API."""
from contextvars import ContextVar

actor_id: ContextVar[str] = ContextVar('qishu_actor_id', default='local-user')
multiuser: ContextVar[bool] = ContextVar('qishu_multiuser', default=False)
