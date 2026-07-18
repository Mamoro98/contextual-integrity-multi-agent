"""Test Layer 1 alone: seed.yaml -> vignette, printed + saved to out/.

Usage:  python test_layer1.py   (from pipeline/shared_context_gen/)
"""
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent          # .../pipeline/shared_context_gen
PIPELINE = HERE.parent                          # .../pipeline
REPO = PIPELINE.parent                          # repo root
for p in (str(REPO / "concordia"), str(PIPELINE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import yaml
from dotenv import load_dotenv
load_dotenv(REPO / ".env")

from src.model_utils import setup_model
from layer1_vignette import generate_vignette

seed_doc = yaml.safe_load((HERE / "seed.yaml").read_text(encoding="utf-8"))
cfg = yaml.safe_load((HERE / "gen_config.yaml").read_text(encoding="utf-8"))

print("model:", cfg["model"])
model = setup_model(cfg["model"])

print("seed:", json.dumps(seed_doc["seed"], indent=2))
print("\n--- generating vignette ---")
vignette = generate_vignette(
    model, seed_doc["seed"],
    requester_role=seed_doc["recast"]["requester_role"],
    temperature=cfg.get("temperature", 0.7),
    max_refine_tries=cfg.get("max_refine_tries", 2))

print("\nSTORY:\n" + vignette["story"])
print("\nCONCRETE SLOTS:")
for k in ("data_type_concrete", "data_subject_concrete", "data_sender_concrete",
          "data_recipient_concrete", "requester_concrete", "safe_payload_concrete"):
    print(f"  {k}: {vignette.get(k)}")
print("\nrefine_round:", vignette.get("refine_round"))
if "story_before_refinement" in vignette:
    print("(story was refined; original kept in the saved JSON)")

out = HERE / "out"
out.mkdir(exist_ok=True)
(out / "vignette_test.json").write_text(
    json.dumps({"seed": seed_doc["seed"], "recast": seed_doc["recast"],
                "scenario_id": seed_doc.get("scenario_id"),
                "vignette": vignette}, indent=2),
    encoding="utf-8")
print("\nsaved -> out/vignette_test.json")
