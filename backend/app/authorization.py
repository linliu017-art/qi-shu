"""Permission policy for multi-user mode; not yet connected to HTTP endpoints."""
from typing import Literal
from sqlalchemy.orm import Session
from .membership import member_role

Action = Literal['read', 'edit', 'submit_review', 'export', 'confirm_requirement',
                 'approve_review', 'manage_members', 'archive']
_MEMBER_ACTIONS = {'read', 'edit', 'submit_review', 'export'}
_OWNER_ACTIONS = _MEMBER_ACTIONS | {'confirm_requirement', 'approve_review', 'manage_members', 'archive'}


def can_access(db: Session, project_id: str, user_id: str, action: Action) -> bool:
    role = member_role(db, project_id, user_id)
    if role == 'owner':
        return action in _OWNER_ACTIONS
    if role == 'member':
        return action in _MEMBER_ACTIONS
    return False
