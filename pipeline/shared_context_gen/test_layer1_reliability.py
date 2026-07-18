"""Reliability test for Layer 1: run the vignette generator N times on the
same seed and apply mechanical checks to every output.

Usage:  python test_layer1_reliability.py [N] [seed_file]
        (defaults: N=5, seed_file=seed.yaml)
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
from common import find_banned_words
from layer1_vignette import generate_vignette

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
SEED_FILE = sys.argv[2] if len(sys.argv) > 2 else "seed.yaml"

seed_doc = yaml.safe_load((HERE / SEED_FILE).read_text(encoding="utf-8"))
print("seed file:", SEED_FILE)
cfg = yaml.safe_load((HERE / "gen_config.yaml").read_text(encoding="utf-8"))
seed = seed_doc["seed"]
requester_role = seed_doc["recast"]["requester_role"]
model = setup_model(cfg["model"])

SLOTS = ["data_type_concrete", "data_subject_concrete", "data_sender_concrete",
         "data_recipient_concrete", "requester_concrete", "safe_payload_concrete"]


def check_vignette(v):
    """Mechanical checks. Returns list of failure strings (empty = pass)."""
    fails = []
    story = v.get("story", "")

    for slot in SLOTS:
        if not str(v.get(slot, "")).strip():
            fails.append(f"empty slot: {slot}")

    if find_banned_words(story):
        fails.append(f"banned words in story: {find_banned_words(story)}")

    # full names: requester and sender need first + last
    for slot in ("requester_concrete", "data_sender_concrete"):
        name = str(v.get(slot, "")).strip()
        if name and len(name.split()) < 2:
            fails.append(f"{slot} not a full name: {name!r}")

    # sender's given first name must be kept
    if seed["data_sender_name"].lower() not in str(v.get("data_sender_concrete", "")).lower():
        fails.append(f"sender lost the seed first name ({seed['data_sender_name']})")

    # subject must be a SINGLE entity: no commas/parentheses, short
    subj = str(v.get("data_subject_concrete", "")).strip()
    if "," in subj or "(" in subj or len(subj.split()) > 5:
        fails.append(f"subject is not a single clean entity: {subj!r}")

    # subject + requester full values must appear verbatim in the story
    for slot in ("data_subject_concrete", "requester_concrete"):
        val = str(v.get(slot, "")).strip()
        if val and val.lower() not in story.lower():
            fails.append(f"{slot} ({val}) not found verbatim in story text")

    # matter_entities must be a non-empty list of strings
    ents = v.get("matter_entities")
    if not isinstance(ents, list) or not ents:
        fails.append(f"matter_entities missing or empty: {ents!r}")

    # noun-phrase slots must be things, not sentences (template composability)
    for slot in ("data_type_concrete", "safe_payload_concrete"):
        val = str(v.get(slot, "")).strip()
        if val.split() and val.split()[0].lower() in ("he", "she", "they", "it"):
            fails.append(f"{slot} is a sentence, not a noun phrase: {val[:60]!r}")

    # sentence-4 richness: at least 3 capitalized multiword entities overall
    import re
    entities = set(re.findall(r"[A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z&.']+)+", story))
    if len(entities) < 4:
        fails.append(f"too few named entities in story ({len(entities)}): {sorted(entities)[:6]}")

    return fails


runs = []
for i in range(N):
    print(f"\n===== run {i+1}/{N} =====")
    try:
        v = generate_vignette(model, seed, requester_role,
                              temperature=cfg.get("temperature", 0.7),
                              max_refine_tries=cfg.get("max_refine_tries", 2))
        fails = check_vignette(v)
        runs.append({"run": i, "ok": not fails, "fails": fails,
                     "refine_round": v.get("refine_round"), "vignette": v})
        status = "PASS" if not fails else "FAIL: " + "; ".join(fails)
        print(f"[{status}] refine_round={v.get('refine_round')}")
        print("  subject:", v.get("data_subject_concrete"))
        print("  requester:", v.get("requester_concrete"))
        print("  story:", v.get("story", "")[:220], "...")
    except Exception as e:
        runs.append({"run": i, "ok": False, "fails": [f"EXCEPTION: {e}"], "vignette": None})
        print("[EXCEPTION]", e)

n_pass = sum(1 for r in runs if r["ok"])
print("\n" + "=" * 60)
print(f"RELIABILITY: {n_pass}/{N} passed all mechanical checks")
for r in runs:
    if not r["ok"]:
        print(f"  run {r['run']}: " + "; ".join(r["fails"]))

out = HERE / "out"
out.mkdir(exist_ok=True)
report_name = f"layer1_reliability__{seed_doc.get('scenario_id', 'unknown')}.json"
(out / report_name).write_text(
    json.dumps({"seed": seed, "n": N, "passed": n_pass, "runs": runs}, indent=2),
    encoding="utf-8")
print(f"saved -> out/{report_name}")
