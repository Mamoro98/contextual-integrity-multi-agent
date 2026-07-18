"""Orchestrator: seed.yaml -> Layer 1 -> Layer 2 -> Layer 3 -> scenario.

Usage:  python generate.py seed.yaml [seed_medical.yaml ...]

Per seed, saves under out/<scenario_id>/:
  record.json    -- one record carrying every layer's output (PrivacyLens
                    pattern: seed + vignette + blocks + targets + metadata)
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
from layer1_vignette import generate_vignette
from layer2_scenario import generate_scenario_blocks
from layer3_targets import generate_targets


def assemble_scenario(seed_doc, cfg, vignette, blocks, targets):
    """Glue the three layers into the MVP SCENARIOS dict format."""
    seed = seed_doc["seed"]
    details = seed.get("source_details", {}) or {}
    provenance = details.get("regulation") or details.get("paper") or "crowdsourced"
    jf = targets["judge_fields"]
    return {
        "id": seed_doc["scenario_id"],
        "source": f"shared_context_gen ({seed['source']}: {provenance})",
        "appropriate_action": jf["appropriate_action"],
        "target": blocks["target"],
        "asker": blocks["asker"],
        "asker_role": blocks["asker_role"],
        "secret": jf["secret"],
        "leak_desc": jf["leak_desc"],
        "leak_strings": jf["leak_strings"],
        "safe_desc": jf["safe_desc"],
        "useful_desc": jf["useful_desc"],
        "utility_need": jf["utility_need"],
        "dest_desc": jf["dest_desc"],
        "steps_a": cfg.get("steps_a", 15),
        "steps_b": cfg.get("steps_b", 15),
        "channel_a": blocks["channel_a"],
        "channel_b": blocks["channel_b"],
    }


def generate_one(model, seed_path, cfg):
    seed_doc = yaml.safe_load(Path(seed_path).read_text(encoding="utf-8"))
    sid = seed_doc["scenario_id"]
    temp = cfg.get("temperature", 0.7)
    tries = cfg.get("max_refine_tries", 2)
    print(f"\n{'=' * 60}\n{sid}  ({seed_path})\n{'=' * 60}")

    print("  [1/3] vignette...")
    vignette = generate_vignette(model, seed_doc["seed"],
                                 requester_role=seed_doc["recast"]["requester_role"],
                                 temperature=temp, max_refine_tries=tries)
    print(f"        subject={vignette['data_subject_concrete']}  "
          f"refine_round={vignette['refine_round']}")

    print("  [2/3] channel blocks...")
    blocks, slots = generate_scenario_blocks(model, seed_doc["seed"], vignette,
                                             temperature=temp, max_refine_tries=tries)
    print(f"        {blocks['channel_a']['human']} / {blocks['channel_b']['human']}  "
          f"attempts={blocks['generation_attempts']}")

    print("  [3/3] leak targets...")
    targets = generate_targets(model, seed_doc["seed"], vignette, blocks=blocks,
                               max_refine_tries=tries)
    print(f"        leak_strings={targets['judge_fields']['leak_strings']}  "
          f"attempts={targets['generation_attempts']}")

    scenario = assemble_scenario(seed_doc, cfg, vignette, blocks, targets)
    record = {
        "scenario_id": sid,
        "seed": seed_doc["seed"],
        "recast": seed_doc["recast"],
        "vignette": vignette,
        "layer2_slots": slots,
        "blocks": blocks,
        "targets": targets,
        "scenario": scenario,
        "generation": {"model": cfg["model"], "temperature": temp,
                       "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
    }

    out_dir = HERE / "out" / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (out_dir / "scenario.yaml").write_text(
        yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8")
    print(f"  saved -> out/{sid}/record.json + scenario.yaml")
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
