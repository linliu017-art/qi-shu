#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMPDIR_TASK="$(mktemp -d /tmp/qishu-restart.XXXXXX)"
PORT=18766
PID=''
cleanup() { if [ -n "$PID" ]; then kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; fi; rm -rf "$TMPDIR_TASK"; }
trap cleanup EXIT
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo '测试端口已被占用，未停止其他进程。'; exit 1; fi
start() {
  (cd "$ROOT/backend" && QISHU_DATA_DIR="$TMPDIR_TASK" DEEPSEEK_API_KEY='' exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT") >"$TMPDIR_TASK/server.log" 2>&1 & PID=$!
  for _ in {1..60}; do if curl -fsS "http://127.0.0.1:$PORT/api/v1/projects" >/dev/null 2>&1; then return; fi; sleep .1; done
  echo '测试服务未能启动。'; exit 1
}
start
echo '测试服务启动。'
RESULT="$(curl -fsS -X POST "http://127.0.0.1:$PORT/api/v1/projects" -H 'Content-Type: application/json' -d '{"name":"重启恢复合成测试"}')"
ID="$(printf '%s' "$RESULT" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
printf '虚构访谈资料：需要统一台账。' > "$TMPDIR_TASK/sample.txt"
MATERIAL="$(curl -fsS -X POST "http://127.0.0.1:$PORT/api/v1/projects/$ID/materials" -F "file=@$TMPDIR_TASK/sample.txt;filename=sample.txt;type=text/plain")"
MATERIAL_ID="$(printf '%s' "$MATERIAL" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
echo '已写入合成项目和资料。'
# 明确标记的测试夹具，只用于验证人工处理和重启；不调用或冒充模型。
FIXTURE_IDS="$(cd "$ROOT/backend" && QISHU_DATA_DIR="$TMPDIR_TASK" DEEPSEEK_API_KEY='' .venv/bin/python - "$ID" "$MATERIAL_ID" <<'PYCODE'
import json, sys
from app.database import SessionLocal
from app.models import AnalysisTask, Requirement, ExtractedFact
with SessionLocal() as db:
    task = AnalysisTask(project_id=sys.argv[1], status='completed', material_ids=json.dumps([sys.argv[2]]))
    db.add(task); db.flush()
    row = Requirement(project_id=sys.argv[1], task_id=task.id, material_id=sys.argv[2], text='模拟建议', original_text='模拟建议', quote='需要统一台账。')
    fact = ExtractedFact(project_id=sys.argv[1], task_id=task.id, material_id=sys.argv[2], text='模拟事实', quote='需要统一台账。')
    db.add_all([row, fact]); db.commit(); print(json.dumps({'requirement_id': row.id, 'fact_id': fact.id}))
PYCODE
)"
REQ_ID="$(printf '%s' "$FIXTURE_IDS" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["requirement_id"])')"
FACT_ID="$(printf '%s' "$FIXTURE_IDS" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["fact_id"])')"
curl -fsS -X PATCH "http://127.0.0.1:$PORT/api/v1/projects/$ID/facts/$FACT_ID/review" -H 'Content-Type: application/json' -d '{"review_status":"reviewed","review_version":0}' > /dev/null
curl -fsS -X PATCH "http://127.0.0.1:$PORT/api/v1/projects/$ID/requirements/$REQ_ID" -H 'Content-Type: application/json' -d '{"status":"confirmed","text":"人工确认的测试需求","version":1}' > /dev/null
BASELINE="$(curl -fsS -X POST "http://127.0.0.1:$PORT/api/v1/projects/$ID/baselines")"
BASELINE_ID="$(printf '%s' "$BASELINE" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
PROPOSAL_ID="$(cd "$ROOT/backend" && QISHU_DATA_DIR="$TMPDIR_TASK" DEEPSEEK_API_KEY='' .venv/bin/python - "$ID" "$BASELINE_ID" <<'PYCODE'
import sys
from app.database import SessionLocal
from app.models import ProposalDraft
from app.main import TEMPLATE_PATH
with SessionLocal() as db:
    draft = ProposalDraft(project_id=sys.argv[1], baseline_id=sys.argv[2], template_id='demo-v1', template_snapshot=TEMPLATE_PATH.read_text(encoding='utf-8'), input_snapshot='{}', model_name='deepseek-flash', status='completed', content='模拟初稿')
    db.add(draft); db.commit(); print(draft.id)
PYCODE
)"
curl -fsS -X PATCH "http://127.0.0.1:$PORT/api/v1/projects/$ID/proposals/$PROPOSAL_ID" -H 'Content-Type: application/json' -d '{"content":"人工修改的模拟初稿","version":1}' > /dev/null
curl -fsS -X POST "http://127.0.0.1:$PORT/api/v1/projects/$ID/proposals/$PROPOSAL_ID/review" -H 'Content-Type: application/json' -d '{"version":2,"action":"submit"}' > /dev/null
curl -fsS -X POST "http://127.0.0.1:$PORT/api/v1/projects/$ID/proposals/$PROPOSAL_ID/review" -H 'Content-Type: application/json' -d '{"version":2,"action":"approve","note":"模拟审核通过","decisions":[],"other_critical_checked":true}' > /dev/null
curl -fsS -X POST "http://127.0.0.1:$PORT/api/v1/projects/$ID/proposals/$PROPOSAL_ID/export" -H 'Content-Type: application/json' -d '{"version":2,"kind":"approved"}' > "$TMPDIR_TASK/synthetic.docx"
echo '已确认人工构造的测试需求并保存清单；未调用模型。'
kill "$PID"; wait "$PID" || true; PID=''
echo '测试服务已停止。'
start
curl -fsS "http://127.0.0.1:$PORT/api/v1/projects" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; rows=json.load(sys.stdin); assert any(x["id"]==sys.argv[1] and x["name"]=="重启恢复合成测试" for x in rows)' "$ID"
curl -fsS "http://127.0.0.1:$PORT/api/v1/projects/$ID/materials/$MATERIAL_ID/original" > "$TMPDIR_TASK/recovered.txt"
cmp "$TMPDIR_TASK/sample.txt" "$TMPDIR_TASK/recovered.txt"
curl -fsS "http://127.0.0.1:$PORT/api/v1/projects/$ID/materials" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; rows=json.load(sys.stdin); assert any(x["id"]==sys.argv[1] and x["text"]=="虚构访谈资料：需要统一台账。" for x in rows)' "$MATERIAL_ID"
curl -fsS "http://127.0.0.1:$PORT/api/v1/projects/$ID/requirements" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; rows=json.load(sys.stdin); assert any(x["id"]==sys.argv[1] and x["text"]=="人工确认的测试需求" and x["status"]=="confirmed" for x in rows)' "$REQ_ID"
curl -fsS "http://127.0.0.1:$PORT/api/v1/projects/$ID/baselines" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; rows=json.load(sys.stdin); assert any(r["text"]=="人工确认的测试需求" for b in rows for r in b["requirements"])'
curl -fsS "http://127.0.0.1:$PORT/api/v1/projects/$ID/facts" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; rows=json.load(sys.stdin); assert any(x["id"]==sys.argv[1] and x["review_status"]=="reviewed" for x in rows)' "$FACT_ID"
curl -fsS "http://127.0.0.1:$PORT/api/v1/projects/$ID/proposals" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; rows=json.load(sys.stdin); assert any(x["id"]==sys.argv[1] and x["content"]=="人工修改的模拟初稿" and x["version"]==2 for x in rows)' "$PROPOSAL_ID"
curl -fsS "http://127.0.0.1:$PORT/api/v1/projects/$ID/proposals/$PROPOSAL_ID/review" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; x=json.load(sys.stdin); assert x["version"]==2 and x["status"]=="approved" and x["note"]=="模拟审核通过"'
"$ROOT/backend/.venv/bin/python" - "$TMPDIR_TASK/synthetic.docx" <<'PYCODE'
import sys
from docx import Document
assert any('已审核方案' in p.text for p in Document(sys.argv[1]).paragraphs)
PYCODE
echo '重启后已找回项目、资料、需求清单、模拟初稿及审核记录；模拟 Word 可读取。'
