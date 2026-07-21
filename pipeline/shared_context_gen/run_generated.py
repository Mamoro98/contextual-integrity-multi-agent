"""Run a GENERATED scenario.yaml through the shared_context_mvp sim.

Usage:  python run_generated.py out/<scenario_id>/scenario.yaml

Executes shared_context_mvp.py cell by cell in one namespace, but swaps
SCENARIOS for the loaded YAML scenario just before the Run cell -- so the
generated scenario goes through the exact same sim + saving code as the
hand-written one (results land in a run_<ts>_<id> folder as usual).
"""
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent          # pipeline/shared_context_gen
PIPELINE = HERE.parent

import os
import yaml

if len(sys.argv) < 2:
    raise SystemExit("usage: python run_generated.py <scenario.yaml>")
scenario_path = Path(sys.argv[1]).resolve()
scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
print(f"loaded generated scenario: {scenario['id']}")
print(f"  secret subject: {scenario['target']}   asker: {scenario['asker']}")
print(f"  secret: {scenario['secret'][:120]}")

# The MVP resolves paths via Path.cwd() -- run from the pipeline dir.
os.chdir(PIPELINE)

mvp_src = (PIPELINE / "shared_context_mvp.py").read_text(encoding="utf-8")
cells = re.split(r"^# In\[.*\]:\s*$", mvp_src, flags=re.MULTILINE)

ns = {"__name__": "__main__"}
for cell in cells:
    if "# --- Run ---" in cell:
        print(f"\n[run_generated] overriding SCENARIOS with {scenario['id']}\n")
        ns["SCENARIOS"] = [scenario]
    exec(compile(cell, "<mvp-cell>", "exec"), ns)

print("\n[run_generated] done.")
