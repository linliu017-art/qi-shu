"""Outline defaults and deterministic scope/structure validation."""
import re
from pydantic import BaseModel, Field, field_validator

class OutlineChapter(BaseModel):
    id: str = Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    title: str = Field(min_length=1,max_length=120)
    instruction: str = Field(default='',max_length=1000)
    requirement_ids: list[str] = Field(default_factory=list,max_length=300)

    @field_validator('title')
    @classmethod
    def valid_title(cls, value):
        value=value.strip()
        if not value or any(c in value for c in '\n\r#<>'):
            raise ValueError('章节标题不能为空，且不能包含换行或标题标记。')
        return value


def default_chapters(template: str, allow_generic: bool = False):
    pattern = r'^##[ \t]+([^#\r\n][^\r\n]*)$' if allow_generic else r'^##\s+([一二三四五六七八九十]+\s+[^\r\n]+)\s*$'
    headings=re.findall(pattern,template,flags=re.M)
    headings = [title.strip().rstrip('#').strip() for title in headings if title.strip()]
    if len(headings)>30 or len(headings)!=len(set(headings)) or any(len(title)>120 or any(c in title for c in '#<>') for title in headings):
        return []
    return [{'id':f'chapter-{i+1}','title':title,'instruction':'','requirement_ids':[]} for i,title in enumerate(headings)]


def validate_chapters(chapters: list[OutlineChapter], requirements: list[dict]):
    valid={x['id'] for x in requirements if isinstance(x,dict) and isinstance(x.get('id'),str)}
    if not valid or len(valid)!=len(requirements):
        raise ValueError('需求清单缺少可核对的需求编号。')
    ids=[c.id for c in chapters];titles=[c.title.strip() for c in chapters]
    if len(ids)!=len(set(ids)) or len(titles)!=len(set(titles)):
        raise ValueError('章节标识或标题不能重复。')
    for chapter in chapters:
        if len(chapter.requirement_ids)!=len(set(chapter.requirement_ids)) or any(i not in valid for i in chapter.requirement_ids):
            raise ValueError('章节关联了不属于本清单的需求或重复需求。')
    assigned={i for chapter in chapters for i in chapter.requirement_ids}
    return [x for x in requirements if x['id'] not in assigned]


def matches_outline(content: str, outline: list[dict]) -> bool:
    """Exact level-two chapter headings in saved order; subsections remain allowed."""
    expected=[entry.get('章节标题','').strip() for entry in outline]
    if not expected or any(not x for x in expected):
        return False
    headings=[];fence=None
    for line in content.splitlines():
        marker=re.match(r'^ {0,3}(`{3,}|~{3,})',line)
        if marker:
            token=marker.group(1)
            if fence is None:fence=(token[0],len(token))
            elif token[0]==fence[0] and len(token)>=fence[1]:fence=None
            continue
        if fence is None:
            m=re.match(r'^ {0,3}##[ \t]+(.+?)[ \t]*#*[ \t]*$',line)
            if m:headings.append(m.group(1).strip())
    return fence is None and headings==expected
