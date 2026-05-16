"""Run benchmark experiments: scenario YAML -> LLM execution -> scored results.

Usage:
    benchmark.py --dir DIR [--config path/to/benchmark.yaml]

Simulation settings (models, prefabs, engine, etc.) are loaded from
pipeline/configs/benchmark.yaml by default.
Override with --config path/to/other.yaml.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import yaml

# Force line-buffered stdout so OK / FAILED / Results lines appear in the log
# immediately, even when benchmark.py's stdout is redirected to a file.
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Add project paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.instantiate import instantiate_from_yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Allow overriding the generated-script output dir via env var so two parallel
# pools (e.g. forward + reverse) don't race on the same .py filename.
_scripts_override = os.environ.get("SCRIPTS_DIR_OVERRIDE")
if _scripts_override:
    SCRIPTS_DIR = Path(_scripts_override)
    if not SCRIPTS_DIR.is_absolute():
        SCRIPTS_DIR = Path(__file__).parent.parent / SCRIPTS_DIR
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
else:
    SCRIPTS_DIR = Path(__file__).parent / "scripts"
RESULTS_BASE = "pipeline/results"
DEFAULT_CONFIG = Path(__file__).parent / "configs" / "benchmark.yaml"


def load_config(config_path: Path) -> dict:
    """Load benchmark config YAML."""
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        "innocent_prefab": data.get("innocent_prefab", "basic__Entity"),
        "adversary_prefab": data.get("adversary_prefab", "basic__Entity"),
        "adversary_prefab_sweep": data.get("adversary_prefab_sweep"),
        "innocent_model": data.get("innocent_model"),
        "adversary_model": data.get("adversary_model"),
        "gm_model": data.get("gm_model"),
        "engine": data.get("engine", "sequential"),
        "acting_order": data.get("acting_order", "fixed"),
        "gm_prefab": data.get("gm_prefab"),
        "max_steps": data.get("max_steps", 30),
        "seeds": data.get("seeds", 1),
        "cognitive_profile": data.get("cognitive_profile"),
    }


def run_one(
    scenario_path: Path,
    model_name: str,
    seed: int,
    cfg: dict,
) -> bool:
    """Instantiate a script from a scenario YAML and run it.

    Returns True on success, False on failure.
    """
    max_steps = cfg["max_steps"]

    # Models from config
    innocent_model = cfg.get("innocent_model") or model_name
    adversary_model = cfg.get("adversary_model") or model_name
    gm_model = cfg.get("gm_model") or model_name

    # Load scenario for agent count display
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario_data = yaml.safe_load(f)
    agents = scenario_data.get("agents", {})
    if "innocents" in agents:
        n_inn = len(agents["innocents"])
        n_adv = len(agents.get("adversaries", agents.get("requestors", [])))
    else:
        n_inn, n_adv = 1, 1

    print(f"\n{'-' * 60}")
    print(f"  Scenario: {scenario_path.stem}")
    print(f"  Seed:     {seed}")
    print(f"  Steps:    {max_steps}")
    print(f"  Agents:   {n_inn} innocent(s) + {n_adv} adversary(ies)")
    print(f"  Models:   innocent={innocent_model}, adversary={adversary_model}, gm={gm_model}")
    print(f"  Prefabs:  innocent={cfg['innocent_prefab']}, adversary={cfg['adversary_prefab']}")
    print(f"  Engine:   {cfg['engine']}, order={cfg['acting_order']}")
    profile = cfg.get("cognitive_profile")
    if profile:
        print(f"  Profile:  {profile}")
    print(f"{'-' * 60}")

    # 1. Instantiate script
    try:
        script_path = instantiate_from_yaml(
            scenario_path,
            model_name=model_name,
            innocent_model=innocent_model,
            adversary_model=adversary_model,
            gm_model=gm_model,
            output_format="script",
            output_dir=SCRIPTS_DIR,
            max_steps=max_steps,
            results_base=RESULTS_BASE,
            innocent_prefabs=[cfg["innocent_prefab"]],
            adversary_prefabs=[cfg["adversary_prefab"]],
            engine_type=cfg["engine"],
            acting_order=cfg["acting_order"],
            gm_prefab=cfg["gm_prefab"],
            cognitive_profile=cfg.get("cognitive_profile"),
        )
        print(f"  Script: {script_path}")
    except Exception as e:
        print(f"  ERROR instantiating script: {e}")
        return False

    # 2. Run the script. Use `-Xfaulthandler -u` so any fatal signal prints a
    # traceback to stderr (caught in log) and stdout is unbuffered.
    cmd = ["uv", "run", "python", "-Xfaulthandler", "-u", str(script_path), "--max-steps", str(max_steps)]
    print(f"  Running: {' '.join(cmd)}", flush=True)
    print(flush=True)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    result = subprocess.run(cmd, cwd=str(Path(__file__).parent.parent), env=env)
    if result.returncode != 0:
        print(f"\n  FAILED (exit code {result.returncode})", flush=True)
        return False

    print(f"\n  OK", flush=True)
    return True


def collect_scenarios(dir_path: Path) -> list[Path]:
    """Collect all .yaml scenario files in a directory (recursive)."""
    scenarios = sorted(dir_path.rglob("*.yaml"))
    if not scenarios:
        print(f"ERROR: No .yaml files found in {dir_path}")
        sys.exit(1)
    return scenarios


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run benchmark experiments: scenario YAML -> LLM -> scored results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # All scenarios in a dir (recursive):
  benchmark.py --dir pipeline/configs/scenarios/bank_account/1i_1a/fc0/

  # With custom config:
  benchmark.py --dir path/to/scenarios/ --config my_config.yaml
""",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", type=str,
                       help="Directory of scenario YAMLs (recursive)")
    group.add_argument("--file", type=str,
                       help="Single scenario YAML file")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG),
                        help=f"Benchmark config YAML (default: {DEFAULT_CONFIG})")
    parser.add_argument("--seeds", type=int, default=None,
                        help="Override seeds count from config")

    args = parser.parse_args()

    if args.file:
        file_path = Path(args.file)
        if not file_path.is_file():
            print(f"ERROR: File not found: {file_path}")
            sys.exit(1)
        dir_path = None
    else:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"ERROR: Directory not found: {dir_path}")
            sys.exit(1)

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}")
        sys.exit(1)
    cfg = load_config(config_path)
    print(f"Config: {config_path}")

    # Validate: need models in config
    if not cfg.get("innocent_model"):
        print("ERROR: Set innocent_model in benchmark config")
        sys.exit(1)

    if args.file:
        scenarios = [Path(args.file)]
    else:
        scenarios = collect_scenarios(dir_path)
    model = cfg["innocent_model"]
    seeds = args.seeds if args.seeds is not None else cfg["seeds"]

    # Determine prefab list: sweep overrides single adversary_prefab
    sweep = cfg.get("adversary_prefab_sweep")
    if sweep:
        prefab_list = list(sweep)
    else:
        prefab_list = [cfg["adversary_prefab"]]

    total = len(prefab_list) * len(scenarios) * seeds

    print(f"\n{'=' * 60}")
    print(f"Benchmark: {dir_path}")
    print(f"  Model: {model}")
    print(f"  Scenarios: {len(scenarios)}, Seeds: {seeds}, Max steps: {cfg['max_steps']}")
    if len(prefab_list) > 1:
        print(f"  Adversary prefab sweep: {prefab_list}")
    print(f"  Total runs: {total}")
    print(f"{'=' * 60}")

    # Track results per (prefab, scenario) for summary table
    # results_tracker[prefab][scenario_stem] = {"ok": int, "fail": int}
    results_tracker: dict[str, dict[str, dict[str, int]]] = {}

    for prefab in prefab_list:
        run_cfg = dict(cfg)
        run_cfg["adversary_prefab"] = prefab

        if len(prefab_list) > 1:
            print(f"\n{'#' * 60}")
            print(f"  PREFAB: {prefab}")
            print(f"{'#' * 60}")

        results_tracker[prefab] = {}
        for scenario in scenarios:
            stem = scenario.stem
            results_tracker[prefab][stem] = {"ok": 0, "fail": 0}
            for seed in range(1, seeds + 1):
                ok = run_one(scenario, model, seed, run_cfg)
                if ok:
                    results_tracker[prefab][stem]["ok"] += 1
                else:
                    results_tracker[prefab][stem]["fail"] += 1

    # ── Summary ─────────────────────────────────────────────────────────
    total_ok = sum(
        v["ok"]
        for p in results_tracker.values()
        for v in p.values()
    )
    print(f"\n{'=' * 60}")
    print(f"Results: {total_ok}/{total} succeeded")
    print(f"{'=' * 60}")

    if len(prefab_list) > 1:
        # Print per-prefab summary table
        all_stems = sorted({
            stem for p in results_tracker.values() for stem in p
        })
        col_w = max(len(s) for s in all_stems) + 2

        header = f"{'Scenario':<{col_w}}"
        for prefab in prefab_list:
            short = prefab.replace("__Entity", "")
            header += f"  {short:>16}"
        print(f"\n{header}")
        print("-" * len(header))

        for stem in all_stems:
            row = f"{stem:<{col_w}}"
            for prefab in prefab_list:
                counts = results_tracker[prefab].get(stem, {"ok": 0, "fail": 0})
                row += f"  {counts['ok']}/{counts['ok'] + counts['fail']:>14}"
            print(row)

        # Totals row
        row = f"{'TOTAL':<{col_w}}"
        for prefab in prefab_list:
            p_ok = sum(v["ok"] for v in results_tracker[prefab].values())
            p_total = sum(v["ok"] + v["fail"] for v in results_tracker[prefab].values())
            row += f"  {p_ok}/{p_total:>14}"
        print("-" * len(header))
        print(row)


if __name__ == "__main__":
    main()
