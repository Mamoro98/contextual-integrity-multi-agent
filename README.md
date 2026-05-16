# A Generative Model of Contextual Integrity

**Appropriate vs. Inappropriate Information Sharing in Multi-Actor LLM Systems**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-TBD-b31b1b.svg)](#)

<!-- arXiv: TBD -->

> Contextual integrity (CI) holds that appropriate information flow depends on
> context-specific norms. The same disclosure may be appropriate in one context
> and inappropriate in another. As actors handle private user data in
> multi-actor pipelines, we ask whether they track these norms faithfully under
> social and contextual pressure. We build **a generative model of CI in
> multi-actor systems**: scenarios drawn from CI's taxonomies, a generation
> pipeline, multi-actor simulation, and a two-sided appropriateness metric. The
> metric scores both withholding when norms forbid sharing and sharing when they
> permit it. Across three intervention axes (decision logic, cognitive profile,
> and model choice), **no actor-level lever closes both sides of the
> appropriateness gap**; protection and utility trade off in every variant we
> tested. Closing the gap may require mechanisms beyond the actor level, such as
> CI-grounded policy and institution design.

**Paper:** see the [latest GitHub release](https://github.com/Mamoro98/contextual-integrity-multi-agent/releases) for the PDF. arXiv: _TBD_.
**Authors:** Omer Ebead · Claude Formanek · Joel Z. Leibo

---

## Quick start

```bash
git clone --recurse-submodules https://github.com/Mamoro98/contextual-integrity-multi-agent.git
cd contextual-integrity-multi-agent
uv sync
cp .env.example .env          # add GEMINI_API_KEY (and OPENAI_API_KEY / OPENROUTER_API_KEY for cross-model runs)
bash run_fc0_parallel.sh      # smallest cell: Type I adversarial scenario(s)
```

Results land in `pipeline/results/<scenario>_fc0/`. Each run writes a
`result.json` (scoring + `experiment_meta`), a `summary.md` digest, and a
rendered `transcript.html`.

If you cloned without `--recurse-submodules`, fetch concordia after the fact:

```bash
git submodule update --init --recursive
```

## Requirements

- Python ≥ 3.12, [`uv`](https://github.com/astral-sh/uv)
- An LLM API key — `GEMINI_API_KEY` covers the main experiments
  (`google/gemini-2.5-flash`). `OPENAI_API_KEY` and `OPENROUTER_API_KEY` are
  only needed for the cross-model configs.

## Repository layout

```
pipeline/
  benchmark.py            entry point: run a scenario under a benchmark config
  generate.py             LLM-driven scenario generator
  run_experiment.py       single-run experiment driver
  configs/
    benchmark_*.yaml      6 main conditions + 4 cross-model conditions
    canonical_data.yaml   canonical private-data items + cognitive profiles
    generation.yaml       scenario-generation settings
    scenarios/            adversarial scenario YAMLs (Types I–III)
    scenarios_appropriate/ appropriate scenario YAMLs (Type IV)
  src/
    instantiate.py        scenario YAML -> runnable Concordia script
    generator.py          generation logic
    validator.py          11-step scenario validation chain
    model_utils.py        model-string parsing + LLM client setup
    schema.py             ScenarioConfig dataclass
run_fc{0,1,2}_parallel.sh launchers for Type I / II / III adversarial cells
run_appropriate_parallel.sh launcher for Type IV (appropriate) cells
upload_results_to_wandb.py  push pipeline/results/ to W&B as an artifact
concordia/                Concordia fork (git submodule)
insights/                 experiment notes
```

## Reproducing the paper

The four launchers each sweep their scenario set across the six main
conditions (`basic`, `trusting`, `skeptical`, `rational`, `rational_trusting`,
`rational_skeptical`):

| Scenario type | Launcher | Result dirs |
|---|---|---|
| Type I — adversarial, no licensing | `bash run_fc0_parallel.sh` | `*_fc0*` |
| Type II — adversarial, partial licensing | `bash run_fc1_parallel.sh` | `*_fc1*` |
| Type III — adversarial, info-flow + TP | `bash run_fc2_parallel.sh` | `*_fc2*` |
| Type IV — appropriate sharing | `bash run_appropriate_parallel.sh` | `*_fc3*` |

To run a single (scenario, condition) cell directly:

```bash
uv run python pipeline/benchmark.py \
  --file pipeline/configs/scenarios/ssn/1i_1a/fc0/archival_cataloging_collaboration_ssn.yaml \
  --config pipeline/configs/benchmark_basic.yaml
```

Cross-model results use the `benchmark_basic_{gemini3,gpt4omini,haiku,maverick}.yaml`
configs in place of `benchmark_basic.yaml`.

### Scenario set

This repository ships the **5 scenarios named in the paper**, one or more per
type:

| Scenario | Type | Target |
|---|---|---|
| `archival_cataloging_collaboration_ssn` | I | SSN |
| `weather_station_coordination_bank_account` | II | bank account |
| `agricultural_consultancy_ssn` | II | SSN |
| `defense_contractor_vetting_ssn` | III | SSN |
| `university_stipend_enrollment_bank_account` | IV | bank account |

The full 36-scenario grid behind the paper's aggregate numbers can be
regenerated with `pipeline/generate.py`.

## Sample results

[`results-sample/`](results-sample/) holds a browsable slice of experiment
outputs — 21 runs across the three intervention axes (decision logic,
cognitive profile, model choice) — so you can inspect the scoring format and
headline effects without re-running anything. See its
[README](results-sample/README.md) for the layout.

## Full results

The complete result set is too large for Git. Upload your own runs to W&B:

```bash
uv run python upload_results_to_wandb.py
```

Published W&B project: _TBD_.

## Citation

```bibtex
@article{ebead2026contextualintegrity,
  title         = {A Generative Model of Contextual Integrity: Appropriate vs. Inappropriate Information Sharing},
  author        = {Ebead, Omer and Formanek, Claude and Leibo, Joel Z.},
  year          = {2026},
  eprint        = {TBD},
  archivePrefix = {arXiv},
  url           = {https://github.com/Mamoro98/contextual-integrity-multi-agent}
}
```

## License

Code is released under the [MIT License](LICENSE). The paper PDF is distributed
under CC-BY-4.0.
