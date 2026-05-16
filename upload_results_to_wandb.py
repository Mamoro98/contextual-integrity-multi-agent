"""Push pipeline/results/ to wandb as a single versioned Artifact.

Usage:
    uv run python upload_results_to_wandb.py [project_name]

Default project: embedded-adversarial
Artifact: results-snapshot (auto-versioned v0, v1, ...)
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import wandb

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

PROJECT = sys.argv[1] if len(sys.argv) > 1 else "embedded-adversarial"
RESULTS_DIR = ROOT / "pipeline" / "results"

if not RESULTS_DIR.is_dir():
    sys.exit(f"ERROR: {RESULTS_DIR} not found")

total_files = sum(1 for _ in RESULTS_DIR.rglob("*") if _.is_file())
total_bytes = sum(f.stat().st_size for f in RESULTS_DIR.rglob("*") if f.is_file())
print(f"Uploading {total_files} files, {total_bytes/1e9:.2f} GB, to wandb project '{PROJECT}'")

run = wandb.init(
    project=PROJECT,
    job_type="results-snapshot",
    name=f"snapshot-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    config={
        "total_files": total_files,
        "total_gb": round(total_bytes / 1e9, 2),
        "source": str(RESULTS_DIR),
    },
)

art = wandb.Artifact(
    "results-snapshot",
    type="results",
    description=f"Full pipeline/results/ snapshot at {datetime.now().isoformat()}",
    metadata={
        "total_files": total_files,
        "total_bytes": total_bytes,
    },
)
art.add_dir(str(RESULTS_DIR))

print("Calling log_artifact(); this will upload and block until done...")
run.log_artifact(art)
art.wait()

print("Upload complete.")
print(f"Pull locally with:  wandb artifact get {PROJECT}/results-snapshot:latest")
run.finish()
