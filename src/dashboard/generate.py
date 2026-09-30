from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

def write_dashboard(payload):
    out=Path("dashboard")
    out.mkdir(parents=True,exist_ok=True)
    data=dict(payload)
    data["generated_at"]=datetime.now(timezone.utc).isoformat()
    (out/"data.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    return out/"data.json"
