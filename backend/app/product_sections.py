"""Locate Markdown sections without changing unrelated PRD content."""
import re

HEADING=re.compile(r'^ {0,3}(#{1,6})[ \t]+(.+?)\s*#*\s*$')
FENCE=re.compile(r'^ {0,3}(`{3,}|~{3,})')

def headings(text:str):
    found=[];offset=0;fence=None
    for line in text.splitlines(keepends=True):
        marker=FENCE.match(line)
        if marker:
            symbol=marker.group(1)
            if fence is None: fence=symbol
            elif symbol[0]==fence[0] and len(symbol)>=len(fence): fence=None
        elif fence is None:
            match=HEADING.match(line.rstrip('\r\n'))
            if match:
                found.append({'title':match.group(2).strip(),'level':len(match.group(1)),
                              'heading_start':offset,'body_start':offset+len(line)})
        offset+=len(line)
    if fence is not None:
        raise ValueError('存在未闭合代码块，无法安全定位章节。')
    for i,item in enumerate(found):
        item['body_end']=next((later['heading_start'] for later in found[i+1:] if later['level']<=item['level']),len(text))
        item['index']=i
    return found

def validate_replacement(text:str, level:int):
    if not text.strip() or len(text)>100000: return False
    try: return not any(item['level']<=level for item in headings(text))
    except ValueError: return False
