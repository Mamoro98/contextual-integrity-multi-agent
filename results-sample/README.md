# Sample results

A small, browsable slice of experiment outputs — enough to see the artifact
format and the headline effects without re-running anything. The **full**
result set lives on Weights & Biases (see the top-level [README](../README.md)).

## What a leaf contains

Every leaf is one simulation run:

| File | Description |
|---|---|
| `result.json` | Full record: scenario config, agent memories, turn-by-turn transcript, and `experiment_meta` with both string-match and LLM-judge scoring. |
| `summary.md` | Human-readable digest: scenario, condition, target outcome, scoring tables. |

A rendered `transcript.html` is produced for every run but omitted here to keep
the repository small; it is fully regenerable from `result.json` and available
for any run on W&B.

## Layout

Leaves are grouped by the paper's three intervention axes. Each leaf is keyed
by extraction target (`bank_account`, `ssn`) and scenario type (`type-II`,
`type-III`).

```
decision-logic/      basic vs rational decision logic
  basic/    rational/
cognitive-profile/   trusting vs skeptical innocent-actor profile
  trusting/ skeptical/
model-choice/        same scenario across 4 models
  gemini-2.5-flash/ gemini-3-flash-preview/ gpt-4o-mini/ llama-4-maverick/
  haiku-decline-example/   Claude Haiku 4.5 declined the task; excluded from
                           the model grid, kept here to document the exclusion.
```

## Coverage

This sample uses the **3 scenarios with complete coverage of all six main
conditions**:

| Scenario | Type | Target |
|---|---|---|
| `weather_station_coordination_bank_account` | II | bank account |
| `agricultural_consultancy_ssn` | II | SSN |
| `defense_contractor_vetting_ssn` | III | SSN |

- `decision-logic/` and `cognitive-profile/` include all 3 scenarios.
- `model-choice/` includes only the 2 scenarios with cross-model runs
  (`agricultural_consultancy_ssn`, `defense_contractor_vetting_ssn`);
  `weather_station_coordination_bank_account` was not run cross-model.
- One seed per leaf. All runs are 30-step, `dialogic` game master.

For Type I / Type IV examples and the remaining scenarios, regenerate with
`pipeline/generate.py` and run the launchers (see the top-level README).
