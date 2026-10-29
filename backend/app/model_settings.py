"""Server-only model configuration. Never return or log the stored API key."""
import json
import os
import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import ModelSettings, ModelSettingsEvent, UserAccount


def model_key() -> str:
    return os.environ.get('DEEPSEEK_API_KEY', '').strip()


def model_settings(db: Session) -> tuple[list[str], int]:
    row = db.execute(select(ModelSettings.allowed_models, ModelSettings.max_requests).where(ModelSettings.id == 1)).first()
    if row:
        return json.loads(row.allowed_models), row.max_requests
    models = [x.strip() for x in os.environ.get('DEEPSEEK_ALLOWED_MODELS', 'deepseek-flash').split(',') if x.strip()]
    return models, int(os.environ.get('QISHU_MAX_REQUESTS', '50'))


def _admin(db: Session, actor_id: str):
    actor = db.get(UserAccount, actor_id)
    if not actor or not actor.active or not actor.is_admin:
        raise PermissionError('无权管理模型配置。')


def save_settings(db: Session, actor_id: str, models: list[str], maximum: int) -> None:
    _admin(db, actor_id)
    models = [x.strip() for x in models]
    if not 1 <= maximum <= 1000 or not 1 <= len(models) <= 20 or len(set(models)) != len(models):
        raise ValueError('模型列表或调用次数不正确。')
    if any(not re.fullmatch(r'deepseek-[A-Za-z0-9][A-Za-z0-9_.-]{0,90}', model) for model in models):
        raise ValueError('模型名称不正确。')
    config = db.get(ModelSettings, 1)
    old = model_settings(db)
    if not config:
        config = ModelSettings(id=1, allowed_models=json.dumps(models), max_requests=maximum)
        db.add(config)
    else:
        config.allowed_models, config.max_requests = json.dumps(models), maximum
    db.add(ModelSettingsEvent(actor_id=actor_id, action='settings_changed',
        details=json.dumps({'old_models':old[0], 'old_max_requests':old[1], 'new_models':models, 'new_max_requests':maximum})))
    db.commit()
