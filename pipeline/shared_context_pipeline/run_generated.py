"""Run a generated scenario through the simulation, then score it with the
LLM judge -- one command for the sim + scoring stage of the pipeline.

Usage:  python run_generated.py generation/scenarios/<id>/scenario.yaml [--no-judge] [--seeds N]
"""
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent            # .../shared_context_pipeline
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import yaml

import simulation
from judge import judge_run, JUDGE_MODEL


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_judge = "--no-judge" in sys.argv
    seeds = 1
    if "--seeds" in sys.argv:
        seeds = int(sys.argv[sys.argv.index("--seeds") + 1])
    if not args:
        raise SystemExit("usage: python run_generated.py <scenario.yaml> [--no-judge] [--seeds N]")

    scenario_path = Path(args[0]).resolve()
    scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    print(f"loaded scenario: {scenario['id']}")
    print(f"  subject: {scenario['target']}   asker: {scenario['asker']}")

    run_dir, _ = simulation.run([scenario], seeds=seeds)

    if not no_judge:
        # Ground truth = the clean noun phrases from the generation record:
        # confidential matter + shareable payload.
        vign = json.loads((scenario_path.parent / "record.json")
                          .read_text(encoding="utf-8"))["vignette"]
        judge_model = simulation.setup_model(JUDGE_MODEL)

        print(f"\njudging with {JUDGE_MODEL}")
        for rj in run_dir.glob("*__result.json"):
            res = json.loads(rj.read_text(encoding="utf-8"))
            verdict = judge_run(judge_model, vign["data_type_concrete"],
                                vign["safe_payload_concrete"],
                                res["assistant_lines_channel_b"])
            (run_dir / (rj.stem.replace("__result", "") + "__verdict.json")).write_text(
                json.dumps(verdict, indent=2), encoding="utf-8")
            print(f"  {rj.stem}: leaked={verdict['leaked']} used={verdict['used_shareable']} "
                  f"-> {verdict['outcome'].upper()}")

    print("\ndone.")


if __name__ == "__main__":
    main()
