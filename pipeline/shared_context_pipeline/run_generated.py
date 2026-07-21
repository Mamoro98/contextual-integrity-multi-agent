"""Run a GENERATED scenario.yaml through the shared_context_mvp sim, then
score it with the LLM judge (judge.py) in the same script.

Usage:  python run_generated.py out/<scenario_id>/scenario.yaml [--no-judge]

Executes shared_context_mvp.py cell by cell in one namespace, but swaps
SCENARIOS for the loaded YAML scenario just before the Run cell -- so the
generated scenario goes through the exact same sim + saving code as the
hand-written one (results land in a run_<ts>_<id> folder as usual). After
the sim, the LLM judge reads the channel-B assistant lines + the Layer-1
story and writes verdict.json into the same run folder.
"""
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent          # .../shared_context_pipeline
REPO = HERE
while not (REPO / "concordia").exists() and REPO != REPO.parent:
    REPO = REPO.parent                          # repo root

import os
import yaml

args = [a for a in sys.argv[1:] if not a.startswith("--")]
NO_JUDGE = "--no-judge" in sys.argv
if not args:
    raise SystemExit("usage: python run_generated.py <scenario.yaml> [--no-judge]")
scenario_path = Path(args[0]).resolve()
scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
print(f"loaded generated scenario: {scenario['id']}")
print(f"  secret subject: {scenario['target']}   asker: {scenario['asker']}")
print(f"  secret: {scenario['secret'][:120]}")

# Run from the repo root; the MVP finds paths by walking up to concordia.
os.chdir(REPO)

mvp_src = (HERE / "shared_context_mvp.py").read_text(encoding="utf-8")
cells = re.split(r"^# In\[.*\]:\s*$", mvp_src, flags=re.MULTILINE)

ns = {"__name__": "__main__"}
for cell in cells:
    if "# --- Run ---" in cell:
        print(f"\n[run_generated] overriding SCENARIOS with {scenario['id']}\n")
        ns["SCENARIOS"] = [scenario]
    exec(compile(cell, "<mvp-cell>", "exec"), ns)

# --- Scoring: LLM judge over the sim we just ran ---
if not NO_JUDGE:
    import json
    sys.path.insert(0, str(HERE))
    from judge import judge_run, JUDGE_MODEL

    run_dir = ns["RUN_DIR"]                       # set by the MVP's Run cell
    model = ns["setup_model"](JUDGE_MODEL)        # reuse the MVP's setup_model
    # The two info lists come from the record's clean vignette noun phrases:
    # confidential = the matter, shareable = the safe payload.
    vign = json.loads((scenario_path.parent / "record.json").read_text(encoding="utf-8"))["vignette"]
    secret = vign["data_type_concrete"]
    safe_payload = vign["safe_payload_concrete"]

    print(f"\n[run_generated] judging with {JUDGE_MODEL}\n")
    for rj in run_dir.glob("*__result.json"):
        res = json.loads(rj.read_text(encoding="utf-8"))
        verdict = judge_run(model, secret, safe_payload,
                            res["assistant_lines_channel_b"])
        (run_dir / (rj.stem.replace("__result", "") + "__verdict.json")).write_text(
            json.dumps(verdict, indent=2), encoding="utf-8")
        print(f"  {rj.stem}: leaked={verdict['leaked']} used={verdict['used_shareable']} "
              f"-> {verdict['outcome'].upper()}")
    print(f"  verdicts saved in {run_dir}")

print("\n[run_generated] done.")
