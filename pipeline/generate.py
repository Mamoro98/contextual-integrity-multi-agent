"""Generate digital scenarios from a config file.

Reads all settings from pipeline/configs/generation.yaml:
  - model, extraction_target, count, agent counts, contextual factors

Usage:
    python pipeline/generate.py
"""

import logging
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Concordia path
CONCORDIA_REPO = os.environ.get(
    "CONCORDIA_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "concordia"),
)
if CONCORDIA_REPO not in sys.path:
    sys.path.insert(0, CONCORDIA_REPO)

from concordia.contrib.language_models.openai.gpt_model import GptLanguageModel
from src.model_utils import compute_cost, log_cost, setup_model

from src.generator import (
    APPROPRIATE_SCENARIOS_DIR,
    SCENARIOS_DIR,
    generate_and_save,
    scan_existing_scenarios,
)
from src.schema import ContextualFactors
from src.validator import validate_scenario

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "configs" / "generation.yaml"


def load_config() -> dict:
    """Load generation config YAML."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)



def generate_with_retry(
    model: GptLanguageModel,
    target: str,
    factors: ContextualFactors,
    existing: list[dict[str, str]],
    n_innocents: int,
    n_adversaries: int,
    max_retries: int = 3,
    scenario_class: str = "adversarial",
) -> dict | None:
    """Generate a scenario, validate (including uniqueness), retry on failure."""
    base_dir = (
        APPROPRIATE_SCENARIOS_DIR if scenario_class == "appropriate"
        else SCENARIOS_DIR
    )
    output_dir = base_dir / target
    for attempt in range(1, max_retries + 1):
        try:
            config = generate_and_save(
                model, target, factors, existing,
                output_dir=output_dir,
                n_innocents=n_innocents, n_adversaries=n_adversaries,
                scenario_class=scenario_class,
            )

            ni = len(config.innocents)
            na = len(config.adversaries)
            factor_dir = output_dir / f"{ni}i_{na}a" / factors.folder_name
            yaml_path = factor_dir / f"{config.scenario_id}.yaml"

            report = validate_scenario(config.to_dict(), model, existing)
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
    cfg = load_config()

    model_name = cfg["model"]
    target = cfg["extraction_target"]
    count = cfg["count"]
    n_innocents = cfg.get("n_innocents", 1)
    n_adversaries = cfg.get("n_adversaries", 1)
    scenario_class = cfg.get("scenario_class", "adversarial")
    factors = ContextualFactors.from_dict(cfg["contextual_factors"])

    print(f"Model: {model_name}")
    print(f"Target: {target}")
    print(f"Scenario class: {scenario_class}")
    print(f"Agents: {n_innocents} innocent(s) + {n_adversaries} adversary(ies)")
    print(f"Factors (fc={factors.factor_count}/3):")
    for line in factors.prompt_lines():
        print(f"  {line}")

    model = setup_model(model_name)

    print(f"\n{'='*60}")
    print(f"Generating {count} scenario(s) for {target}")
    print(f"{'='*60}")

    generated = 0
    for i in range(count):
        # Re-scan before each generation so new scenarios are included
        existing = scan_existing_scenarios(
            target, factors.folder_name, scenario_class,
        )
        if existing:
            print(f"\n  ({len(existing)} existing scenario(s) for dedup)")

        print(f"\n--- Scenario {i+1}/{count} ---")
        result = generate_with_retry(
            model, target, factors, existing,
            n_innocents, n_adversaries,
            scenario_class=scenario_class,
        )
        if result:
            generated += 1

    print(f"\n{'='*60}")
    print(f"Done: {generated}/{count} scenario(s) generated for {target}")
    if hasattr(model, "total_input_tokens"):
        cost = compute_cost(model_name, model.total_input_tokens, model.total_output_tokens)
        print(f"Tokens: {model.total_input_tokens:,} in / {model.total_output_tokens:,} out ({model.call_count} calls)")
        print(f"Estimated cost: ${cost:.4f}")
        log_cost(
            task="generation",
            model_name=model_name,
            input_tokens=model.total_input_tokens,
            output_tokens=model.total_output_tokens,
            call_count=model.call_count,
            cost_usd=cost,
            target=target,
            scenarios_generated=generated,
        )
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
