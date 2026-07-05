"""Run a full experiment: generate scenarios then benchmark them.

All settings come from config files:
  - pipeline/configs/generation.yaml  (model, target, count, agent counts)
  - pipeline/configs/factors/{target}.yaml  (contextual factors)
  - pipeline/configs/benchmark.yaml  (simulation settings, seeds)

Usage:
  uv run python pipeline/run_experiment.py
  uv run python pipeline/run_experiment.py --gen-config path/to/generation.yaml --bench-config path/to/benchmark.yaml
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CONCORDIA_REPO = os.environ.get(
    "CONCORDIA_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "concordia"),
)
if CONCORDIA_REPO not in sys.path:
    sys.path.insert(0, CONCORDIA_REPO)

from concordia.contrib.language_models.openai.gpt_model import GptLanguageModel
from src.model_utils import compute_cost, log_cost, setup_model

from src.generator import SCENARIOS_DIR, generate_and_save, load_factors
from src.schema import ContextualFactors
from src.validator import validate_scenario

DEFAULT_GEN_CONFIG = Path(__file__).parent / "configs" / "generation.yaml"
DEFAULT_BENCH_CONFIG = Path(__file__).parent / "configs" / "benchmark.yaml"
SCRIPTS_DIR = Path(__file__).parent / "scripts"
PROJECT_ROOT = Path(__file__).parent.parent


def load_generation_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        "model": data.get("model", "google/gemini-2.5-flash"),
        "extraction_target": data.get("extraction_target", "bank_account"),
        "count": data.get("count", 3),
        "n_innocents": data.get("n_innocents", 1),
        "n_adversaries": data.get("n_adversaries", 1),
    }


def load_benchmark_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)




def generate_with_retry(
    model: GptLanguageModel,
    target: str,
    factors: ContextualFactors,
    output_dir: Path,
    max_retries: int = 3,
    n_innocents: int = 1,
    n_adversaries: int = 1,
) -> dict | None:
    """Generate a scenario and validate, retrying only on validation failures."""
    for attempt in range(1, max_retries + 1):
        try:
            config = generate_and_save(
                model, target, factors, output_dir=output_dir,
                n_innocents=n_innocents, n_adversaries=n_adversaries,
            )
            ni = len(config.innocents)
            na = len(config.adversaries)
            agent_dir = output_dir / f"{ni}i_{na}a"
            factor_dir = agent_dir / factors.folder_name
            yaml_path = factor_dir / f"{config.scenario_id}.yaml"

            report = validate_scenario(config.to_dict(), model)
            print(report.summary())

            if report.all_passed:
                print(f"  YAML saved: {yaml_path}")
                return config

            if yaml_path.exists():
                yaml_path.unlink()
                print(f"  Removed failed YAML: {yaml_path}")

            if attempt < max_retries:
                print(f"  Retrying ({attempt}/{max_retries})...")

        except Exception as e:
            print(f"  ERROR: {e}")
            print(f"  Not retrying (non-validation error)")
            return None

    print(f"  FAILED after {max_retries} attempts")
    return None


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run full experiment: generate scenarios then benchmark",
    )
    parser.add_argument("--gen-config", type=Path, default=DEFAULT_GEN_CONFIG,
                        help="Generation config YAML")
    parser.add_argument("--bench-config", type=Path, default=DEFAULT_BENCH_CONFIG,
                        help="Benchmark config YAML")
    args = parser.parse_args()

    # ── Load configs ─────────────────────────────────────────────────────
    gen_cfg = load_generation_config(args.gen_config)
    bench_cfg = load_benchmark_config(args.bench_config)

    target = gen_cfg["extraction_target"]
    count = gen_cfg["count"]
    n_innocents = gen_cfg["n_innocents"]
    n_adversaries = gen_cfg["n_adversaries"]

    # Load factors
    try:
        factors = load_factors(target)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print("=" * 60)
    print("EXPERIMENT")
    print("=" * 60)
    print(f"  Target:     {target}")
    print(f"  Factors:    fc={factors.factor_count}/3 ({', '.join(factors.active_factors) or 'none'})")
    print(f"  Agents:     {n_innocents}i + {n_adversaries}a")
    print(f"  Scenarios:  {count}")
    print(f"  Seeds:      {bench_cfg.get('seeds', 1)}")
    print(f"  Max steps:  {bench_cfg.get('max_steps', 30)}")
    print(f"  Gen model:  {gen_cfg['model']}")
    print(f"  Innocent:   {bench_cfg.get('innocent_model', 'N/A')}")
    print(f"  Adversary:  {bench_cfg.get('adversary_model', 'N/A')}")
    print(f"  GM:         {bench_cfg.get('gm_model', 'N/A')}")
    print("=" * 60)

    # ── Phase 1: Generate scenarios ──────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"PHASE 1: GENERATING {count} SCENARIO(S)")
    print(f"{'=' * 60}")

    model = setup_model(gen_cfg["model"])
    output_dir = SCENARIOS_DIR / target

    generated = []
    for i in range(count):
        print(f"\n--- Scenario {i+1}/{count} ---")
        config = generate_with_retry(
            model, target, factors, output_dir,
            n_innocents=n_innocents, n_adversaries=n_adversaries,
        )
        if config is None:
            print(f"\nEXPERIMENT ABORTED: scenario {i+1} failed to generate.")
            sys.exit(1)
        generated.append(config)

    # Determine the scenario folder
    ni = gen_cfg["n_innocents"]
    na = gen_cfg["n_adversaries"]
    scenario_dir = output_dir / f"{ni}i_{na}a" / factors.folder_name

    print(f"\n{'=' * 60}")
    print(f"PHASE 1 COMPLETE: {len(generated)} scenario(s) in {scenario_dir}")
    if hasattr(model, "total_input_tokens"):
        cost = compute_cost(gen_cfg["model"], model.total_input_tokens, model.total_output_tokens)
        print(f"Tokens: {model.total_input_tokens:,} in / {model.total_output_tokens:,} out ({model.call_count} calls)")
        print(f"Estimated cost: ${cost:.4f}")
        log_cost(
            task="generation",
            model_name=gen_cfg["model"],
            input_tokens=model.total_input_tokens,
            output_tokens=model.total_output_tokens,
            call_count=model.call_count,
            cost_usd=cost,
            target=target,
        )
    print(f"{'=' * 60}")

    # ── Phase 2: Run benchmark ───────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"PHASE 2: BENCHMARKING")
    print(f"{'=' * 60}")

    cmd = [
        "uv", "run", "python",
        str(Path(__file__).parent / "benchmark.py"),
        "--config", str(args.bench_config),
        "multi",
        "--dir", str(scenario_dir),
    ]
    print(f"  Command: {' '.join(cmd)}")
    print()

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)

    if result.returncode != 0:
        print(f"\nBENCHMARK FAILED (exit code {result.returncode})")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"EXPERIMENT COMPLETE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
