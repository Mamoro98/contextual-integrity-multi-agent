"""Test Layer 3 alone: saved blocks (out/blocks_test.json) -> leak targets.

Usage:  python test_layer3.py [blocks_json]
        (default: out/blocks_test.json -- produce it with test_layer2.py)
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
from layer3_targets import generate_targets, check_targets

src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "out" / "blocks_test.json"
doc = json.loads(src.read_text(encoding="utf-8"))
seed, vignette, blocks = doc["seed"], doc["vignette"], doc["blocks"]
cfg = yaml.safe_load((HERE / "gen_config.yaml").read_text(encoding="utf-8"))

model = setup_model(cfg["model"])
print("story:", vignette["story"][:150], "...\n")
print("--- extracting targets ---")
result = generate_targets(model, seed, vignette, blocks=blocks,
                          max_refine_tries=cfg.get("max_refine_tries", 2))

print(f"\nattempts: {result['generation_attempts']}")
print("\nSENSITIVE FACTS:")
for it in result["extraction"]["sensitive_info_items"]:
    print("  -", it)
print("\nLEAK STRINGS:", result["judge_fields"]["leak_strings"])
if result["dropped_strings"]:
    print("DROPPED:")
    for s, why in result["dropped_strings"].items():
        print(f"  - {s!r}: {why}")
print("\nJUDGE FIELDS:")
for k in ("secret", "leak_desc", "safe_desc", "useful_desc", "utility_need",
          "dest_desc", "appropriate_action"):
    print(f"  {k}: {result['judge_fields'][k][:160]}")

residual = check_targets(result, vignette)
print("\nfinal check:", "CLEAN" if not residual else residual)

out = HERE / "out"
out.mkdir(exist_ok=True)
(out / "targets_test.json").write_text(json.dumps(
    {"seed": seed, "vignette": vignette, "blocks": blocks, "targets": result},
    indent=2), encoding="utf-8")
print("saved -> out/targets_test.json")
