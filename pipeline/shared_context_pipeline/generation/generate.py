"""Orchestrator: seed.yaml -> Layer 1 (vignette) -> Layer 2 (channels) -> scenario.

Usage:  python generate.py seed.yaml [seed_medical.yaml ...]

Scoring/judge fields removed with layer 3 -- scoring will be done later by
an LLM judge reading transcripts directly.

Per seed, saves under out/<scenario_id>/:
  record.json    -- one record carrying every layer's output (PrivacyLens
                    pattern: seed + vignette + blocks + metadata)
  scenario.yaml  -- the final scenario, drop-in compatible with
                    shared_context_mvp.py's SCENARIOS list
"""
import json
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent          # .../shared_context_pipeline/generation
REPO = HERE
while not (REPO / "concordia").exists() and REPO != REPO.parent:
    REPO = REPO.parent                          # repo root (has concordia + pipeline)
for p in (str(REPO / "concordia"), str(REPO / "pipeline"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import yaml
from dotenv import load_dotenv
load_dotenv(REPO / ".env")

from src.model_utils import setup_model
from layer1_vignette import generate_vignette
from layer2_scenario import generate_scenario_blocks


def assemble_scenario(seed_doc, cfg, vignette, blocks):
    """Glue layers 1+2 into the MVP SCENARIOS dict format (no scoring fields)."""
    seed = seed_doc["seed"]
    details = seed.get("source_details", {}) or {}
    provenance = details.get("regulation") or details.get("paper") or "crowdsourced"
    return {
        "id": seed_doc["scenario_id"],
        "source": f"shared_context_gen ({seed['source']}: {provenance})",
        "appropriate_action": (f"share {vignette['safe_payload_concrete']}; "
                               f"withhold {vignette['data_type_concrete']}"),
        "secret": vignette["data_type_concrete"],
        "target": blocks["target"],
        "asker": blocks["asker"],
        "asker_role": blocks["asker_role"],
        "steps_a": cfg.get("steps_a", 15),
        "steps_b": cfg.get("steps_b", 15),
        "channel_a": blocks["channel_a"],
        "channel_b": blocks["channel_b"],
    }


def generate_one(model, seed_path, cfg):
    sp = Path(seed_path)
    if not sp.exists():
        sp = HERE / seed_path                   # allow bare seed names from any cwd
    seed_doc = yaml.safe_load(sp.read_text(encoding="utf-8"))
    sid = seed_doc["scenario_id"]
    temp = cfg.get("temperature", 0.7)
    tries = cfg.get("max_refine_tries", 2)
    print(f"\n{'=' * 60}\n{sid}  ({seed_path})\n{'=' * 60}")

    print("  [1/2] vignette...")
    vignette = generate_vignette(model, seed_doc["seed"],
                                 requester_role=seed_doc["recast"]["requester_role"],
                                 temperature=temp, max_refine_tries=tries)
    print(f"        subject={vignette['data_subject_concrete']}  "
          f"refine_round={vignette['refine_round']}")

    print("  [2/2] channel blocks...")
    blocks, slots = generate_scenario_blocks(model, seed_doc["seed"], vignette,
                                             temperature=temp, max_refine_tries=tries)
    print(f"        {blocks['channel_a']['human']} / {blocks['channel_b']['human']}  "
          f"attempts={blocks['generation_attempts']}")

    scenario = assemble_scenario(seed_doc, cfg, vignette, blocks)
    record = {
        "scenario_id": sid,
        "seed": seed_doc["seed"],
        "recast": seed_doc["recast"],
        "vignette": vignette,
        "layer2_slots": slots,
        "blocks": blocks,
        "scenario": scenario,
        "generation": {"model": cfg["model"], "temperature": temp,
                       "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
    }

    out_dir = HERE / "scenarios" / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (out_dir / "scenario.yaml").write_text(
        yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8")
    print(f"  saved -> scenarios/{sid}/record.json + scenario.yaml")
    return sid, True, None


def main():
    seed_files = sys.argv[1:] or ["seed.yaml"]
    cfg = yaml.safe_load((HERE / "gen_config.yaml").read_text(encoding="utf-8"))
    model = setup_model(cfg["model"])

    results = []
    for sf in seed_files:
        try:
            results.append(generate_one(model, sf, cfg))
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append((sf, False, str(e)))

    print(f"\n{'=' * 60}\nSUMMARY")
    for sid, ok, err in results:
        print(f"  {'OK  ' if ok else 'FAIL'} {sid}" + (f"  ({err[:120]})" if err else ""))


if __name__ == "__main__":
    main()
