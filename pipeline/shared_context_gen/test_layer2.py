"""Test Layer 2 alone: saved vignette (out/vignette_test.json) -> channel blocks.

Usage:  python test_layer2.py [vignette_json]
        (default: out/vignette_test.json -- produce it with test_layer1.py)
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
from layer2_scenario import generate_scenario_blocks, check_blocks

vign_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "out" / "vignette_test.json"
doc = json.loads(vign_path.read_text(encoding="utf-8"))
seed, vignette = doc["seed"], doc["vignette"]
cfg = yaml.safe_load((HERE / "gen_config.yaml").read_text(encoding="utf-8"))

model = setup_model(cfg["model"])
print("vignette:", vignette["story"][:180], "...\n")
print("--- generating channel blocks ---")
blocks, slots = generate_scenario_blocks(
    model, seed, vignette,
    temperature=cfg.get("temperature", 0.7),
    max_refine_tries=cfg.get("max_refine_tries", 2))

print(f"\nattempts: {blocks['generation_attempts']}")
print(f"target: {blocks['target']}   asker: {blocks['asker']}")
print(f"asker_role: {blocks['asker_role']}")
for ch in ("channel_a", "channel_b"):
    b = blocks[ch]
    print(f"\n=== {ch} ({b['human']}) ===")
    print("GOAL:", b["human_goal"])
    print("PREMISE:", b["premise"])
    print("MEMORIES:")
    for m in b["human_memories"]:
        print("  -", m)

residual = check_blocks(blocks, vignette)
print("\nfinal check:", "CLEAN" if not residual else residual)

out = HERE / "out"
out.mkdir(exist_ok=True)
(out / "blocks_test.json").write_text(
    json.dumps({"seed": seed, "vignette": vignette, "slots": slots,
                "blocks": blocks}, indent=2),
    encoding="utf-8")
print("saved -> out/blocks_test.json")
