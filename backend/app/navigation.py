"""Bounded intent classification: navigation destinations remain code-controlled."""
import json
from pathlib import Path
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

Intent = Literal['projects','new_project','worklist','review_todos','materials','requirements','proposal','review','project_settings','workspace_settings','unknown']

class NavigationInterpretInput(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    confirm_external_use: bool = False

class Classification(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    intent: Intent
    project_hint: str = Field(max_length=100)

class NavigationInterpretOutput(Classification):
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

class NavigationModelError(Exception):
    pass

def interpret_navigation(text: str, key: str, model: str) -> NavigationInterpretOutput:
    prompt = (Path(__file__).parent/'prompts'/'navigation_v1.txt').read_text(encoding='utf-8')
    payload = {'model':model,'max_tokens':200,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'},
               'messages':[{'role':'system','content':prompt},{'role':'user','content':text}]}
    for attempt in range(2):
        try:
            response = httpx.post('https://api.deepseek.com/chat/completions', headers={'Authorization':'Bearer '+key}, json=payload, timeout=12)
            if response.status_code >= 500 or response.status_code == 429:
                response.raise_for_status()
            if response.status_code >= 400:
                raise NavigationModelError('模型服务暂时不可用，请使用本地导航。')
            body = response.json()
            choice = body['choices'][0]
            if choice.get('finish_reason') == 'length': raise ValueError('truncated')
            result = Classification.model_validate_json(choice['message']['content'])
            hint = result.project_hint.strip()
            if hint and hint not in text: hint = ''
            usage = body.get('usage') or {}
            def count(name):
                v = usage.get(name)
                return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None
            return NavigationInterpretOutput(intent=result.intent, project_hint=hint, model=model,
                prompt_tokens=count('prompt_tokens'), completion_tokens=count('completion_tokens'))
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
            if attempt == 1: raise NavigationModelError('模型服务暂时不可用，请使用本地导航。') from None
        except (KeyError, IndexError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
            raise NavigationModelError('没有识别出可用导航，请换个说法。') from None
    raise NavigationModelError('模型服务暂时不可用，请使用本地导航。')
