"""Reliability test for Layer 2: run block generation N times on the same
saved vignette and report pass/fail + attempts for every run.

Usage:  python test_layer2_reliability.py [N] [source_json]
        source_json: out/vignette_test.json (default) or a
        layer1_reliability__*.json file (first PASSING vignette is used).
"""
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent
REPO = PIPELINE.parent
for p in (str(REPO / "concordia"), str(PIPELINE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import yaml
from dotenv import load_dotenv
load_dotenv(REPO / ".env")

from src.model_utils import setup_model
from layer2_scenario import generate_scenario_blocks

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
SRC = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "out" / "vignette_test.json"

doc = json.loads(SRC.read_text(encoding="utf-8"))
if "vignette" in doc:
    seed, vignette = doc["seed"], doc["vignette"]
elif "runs" in doc:
    seed = doc["seed"]
    vignette = next(r["vignette"] for r in doc["runs"] if r["ok"])
else:
    raise SystemExit(f"unrecognized source format: {SRC}")

cfg = yaml.safe_load((HERE / "gen_config.yaml").read_text(encoding="utf-8"))
model = setup_model(cfg["model"])

print("source:", SRC.name)
print("vignette:", vignette["story"][:150], "...")

runs = []
for i in range(N):
    print(f"\n===== run {i+1}/{N} =====")
    try:
        blocks, slots = generate_scenario_blocks(
            model, seed, vignette,
            temperature=cfg.get("temperature", 0.7),
            max_refine_tries=cfg.get("max_refine_tries", 2))
        runs.append({"run": i, "ok": True, "attempts": blocks["generation_attempts"],
                     "blocks": blocks})
        print(f"[PASS] attempts={blocks['generation_attempts']}")
        print("  goal_b:", blocks["channel_b"]["human_goal"][:160], "...")
    except Exception as e:
        runs.append({"run": i, "ok": False, "error": str(e), "blocks": None})
        print("[FAIL]", str(e)[:300])

n_pass = sum(1 for r in runs if r["ok"])
attempts = [r["attempts"] for r in runs if r.get("ok")]
print("\n" + "=" * 60)
print(f"RELIABILITY: {n_pass}/{N} succeeded; attempts per success: {attempts}")
for r in runs:
    if not r["ok"]:
        print(f"  run {r['run']}: {r['error'][:200]}")

out = HERE / "out"
out.mkdir(exist_ok=True)
name = f"layer2_reliability__{SRC.stem}.json"
(out / name).write_text(json.dumps({"n": N, "passed": n_pass, "runs": runs}, indent=2),
                        encoding="utf-8")
print(f"saved -> out/{name}")
