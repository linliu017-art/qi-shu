#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASK_TMP="$(mktemp -d /tmp/qishu-multi-restart.XXXXXX)"
PORT=18768
PID=''
cleanup() { if [ -n "$PID" ]; then kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; fi; rm -rf "$TASK_TMP"; }
trap cleanup EXIT
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo '多人重启测试端口已占用，未停止其他进程。'; exit 1; fi
start() {
  (cd "$ROOT/backend" && QISHU_DATA_DIR="$TASK_TMP" QISHU_EXPERIMENTAL_MULTIUSER=1 QISHU_ALLOWED_ORIGINS=http://127.0.0.1:13001 DEEPSEEK_API_KEY='' exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT") >"$TASK_TMP/server.log" 2>&1 & PID=$!
  for _ in {1..80}; do if curl -fsS "http://127.0.0.1:$PORT/api/v1/auth/setup-status" >/dev/null 2>&1; then return; fi; sleep .1; done
  echo '多人重启测试服务未能启动。'; exit 1
}
start
ORIGIN='Origin: http://127.0.0.1:13001'
BASE="http://127.0.0.1:$PORT/api/v1"
BODY='{"username":"虚构测试管理员","password":"测试专用且足够长的临时密码"}'
curl -fsS -X POST "$BASE/auth/setup" -H "$ORIGIN" -H 'Content-Type: application/json' -d "$BODY" > /dev/null
curl -fsS -X POST "$BASE/auth/login" -H "$ORIGIN" -H 'Content-Type: application/json' -c "$TASK_TMP/cookies" -d "$BODY" > /dev/null
PROJECT="$(curl -fsS -X POST "$BASE/projects" -H "$ORIGIN" -H 'Content-Type: application/json' -b "$TASK_TMP/cookies" -d '{"name":"多人重启虚构项目"}')"
PROJECT_ID="$(printf '%s' "$PROJECT" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
USER_ID="$(curl -fsS "$BASE/auth/me" -b "$TASK_TMP/cookies" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
printf '多人重启测试资料。' > "$TASK_TMP/sample.txt"
MATERIAL="$(curl -fsS -X POST "$BASE/projects/$PROJECT_ID/materials" -H "$ORIGIN" -b "$TASK_TMP/cookies" -F "file=@$TASK_TMP/sample.txt;filename=sample.txt;type=text/plain")"
MATERIAL_ID="$(printf '%s' "$MATERIAL" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
IDS="$(cd "$ROOT/backend" && QISHU_DATA_DIR="$TASK_TMP" DEEPSEEK_API_KEY='' .venv/bin/python - "$PROJECT_ID" "$USER_ID" <<'PYCODE'
import json,sys
from app.database import SessionLocal
from app.models import AnalysisTask, QueuedJob
with SessionLocal() as db:
    task=AnalysisTask(project_id=sys.argv[1], material_ids='[]', status='running')
    db.add(task); db.flush()
    job=QueuedJob(project_id=sys.argv[1], user_id=sys.argv[2], kind='requirements', target_id=task.id, status='running')
    db.add(job); db.commit()
    print(json.dumps({'task':task.id,'job':job.id}))
PYCODE
)"
TASK_ID="$(printf '%s' "$IDS" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys;print(json.load(sys.stdin)["task"])')"
JOB_ID="$(printf '%s' "$IDS" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys;print(json.load(sys.stdin)["job"])')"
kill "$PID"; wait "$PID" || true; PID=''
start
curl -fsS "$BASE/projects" -b "$TASK_TMP/cookies" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; assert any(p["id"]==sys.argv[1] and p["role"]=="owner" for p in json.load(sys.stdin))' "$PROJECT_ID"
curl -fsS "$BASE/projects/$PROJECT_ID/materials/$MATERIAL_ID/original" -b "$TASK_TMP/cookies" > "$TASK_TMP/recovered.txt"
cmp "$TASK_TMP/sample.txt" "$TASK_TMP/recovered.txt"
curl -fsS "$BASE/projects/$PROJECT_ID/requirement-tasks/$TASK_ID" -b "$TASK_TMP/cookies" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; assert json.load(sys.stdin)["status"]=="interrupted"'
curl -fsS "$BASE/projects/$PROJECT_ID/queue" -b "$TASK_TMP/cookies" | "$ROOT/backend/.venv/bin/python" -c 'import json,sys; assert any(j["id"]==sys.argv[1] and j["status"]=="interrupted" for j in json.load(sys.stdin))' "$JOB_ID"
echo '多人模式重启后账号、项目权限、资料原件已恢复；运行中任务标为中断，未自动重复调用。'
