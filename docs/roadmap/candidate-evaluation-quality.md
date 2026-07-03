# Part G — Candidate Evaluation and Quality Policy

Status: final foundation contract. G1–G9 are implemented; G10 locks their
interfaces and interpretation for later roadmap parts.

## Contract Surface

Part G is a library-level evaluation system. Its public contract modules are:

| Module | Contract |
| --- | --- |
| `strata.core.candidate_evaluation` | Versioned manifests, tasks, tiers, and path-safe loading |
| `strata.core.stage_report` | Shared JSON-ready stage measurement |
| `strata.core.candidate_metrics` | Tier-aware quality metrics at K |
| `strata.core.candidate_baseline` | Current-engine fixture baseline |
| `strata.core.probe_pool` | Mixed obvious and independent rescue pool |
| `strata.core.probe_scoring` | Normalized score components and final-score math |
| `strata.core.content_probe` | Root-contained bounded content windows |
| `strata.core.probe_evaluation` | Baseline, pool, and probed-strategy comparison |

These modules produce immutable or JSON-ready values and do not alter product
candidate selection, CLI behavior, or workflow behavior. Consumers may compose
them for experiments, but promotion into product behavior requires a later
roadmap decision backed by the same metrics and cost reports.

## Locked Part G Policies

### Fixtures, Manifests, and Expected Tiers

- Part G fixtures are tiny, deterministic, synthetic, license-safe repositories
  under `tests/fixtures/candidate_quality`. Manifests live outside each `repo/`
  inventory root.
- The manifest schema version is `1`. Required task fields are ID, task text,
  fixture path, stack/language/framework tags, and all four expected-file tiers.
- `critical` means required for a correct task result. `useful` means valuable
  supporting context. `distractor` means plausible but misleading context.
  `irrelevant` means unrelated context.
- Every tier key is required even when its array is empty. A file may occur in
  only one tier. Optional notes explain tier placement.
- Fixture and expected-file paths are normalized relative paths. Absolute paths,
  parent traversal, unknown fields, duplicate task IDs, and duplicate tier paths
  are contract errors.

### Measurement and Quality

- Any evaluation stage doing meaningful work uses `StageReport` for inputs,
  outputs, metrics, warnings, skipped items, confidence, elapsed milliseconds,
  bytes read, and files touched.
- Reports preserve deterministic key and item ordering. Reproducible runs use
  zero elapsed time unless a monotonic clock is explicitly injected.
- The authoritative quality metrics are critical recall at K, useful coverage
  at K, distractor rate at K, missed critical count, and context waste at K.
- Paths are deduplicated before K. Unknown selected paths count as context waste.
  Empty critical/useful tiers have coverage `1.0`; empty evaluated selections
  have zero distractor and waste rates.
- Critical recall has priority over plain precision because missing required
  evidence can make an otherwise tidy context unusable.

### Baseline, Pool, Score, and Probe

- The baseline is a measurement of the unchanged current candidate engine. It
  is the reference, not a new selector.
- The mixed pool preserves current-engine order in its obvious lane and adds an
  independently ranked rescue lane from structural path evidence. Rescue entry
  does not require or inherit a high current-engine score.
- Initial pool caps are 40 total, 20 obvious, 20 rescue, and 5 per directory.
  These are explicit experimental defaults, not hidden product thresholds.
- Cheap, probe, structural, and cost components are finite normalized values in
  `0.0–1.0`. Default weights are `0.35`, `0.30`, `0.20`, and `0.15`, with cost
  subtracted. Custom weights remain normalized and sum to `1.0`.
- Confidence values are `unknown`, `low`, `medium`, and `high`. Confidence is
  metadata only and is not an additive score, multiplier, or sorting boost.
- The content probe reads only a leading bounded window inside its supplied
  root. Defaults are 20 open attempts, 4 KiB per file, 32 KiB total, and a
  256 KiB maximum eligible file size.
- Missing, oversized, unsafe, non-regular, unreadable, binary, and non-UTF-8
  files are deterministic skipped results. Bytes already read still count.
  Paths after file/byte caps are skipped without filesystem access.

### Comparison and Cost Decision

- G9 compares `baseline`, `mixed_pool`, and `mixed_pool_probe` with the same
  fixtures, K, tier metrics, and stage-cost vocabulary.
- Quality reports never hide cost. Aggregate output retains average recall and
  coverage, missed-critical totals, distractor/waste rates, bytes, and touches.
- “Probe earned its cost” compares `mixed_pool_probe` with `mixed_pool` to
  isolate incremental reads. It is true when critical recall improves, missed
  critical files decrease, or critical performance is unchanged while useful
  coverage improves without greater context waste.
- The decision flag is an initial interpretation, not a product rollout switch.
  Raw per-task quality and cost evidence remains authoritative.

## Downstream Dependencies and Validation Placement

- Part H import tracing may consume mixed pools, probe evidence, normalized
  paths, and `StageReport`; it must not reinterpret expected tiers or silently
  bypass probe caps.
- Part I representation and lazy-outline work may consume ranked/probed entries
  and cost measurements; every representation level must preserve source paths,
  bounded work, and skipped-state reporting.
- Part J frontend deep linking and Part K backend intelligence may extend fixture
  coverage and structural evidence. They must continue grading with the G4
  metrics and must not turn confidence into score.
- H/I/J/K changes that affect candidate evidence should add synthetic manifests
  or tasks and compare against the locked current-engine baseline before any
  product integration.

Real GitHub repository benchmarking is not part of Part G. Part G must not clone
or present synthetic fixtures as real-repository product validation. Controlled
real-repository product validation belongs after Parts M and N, when the product
paths are integrated, and must be repeated after Part P for release-readiness
evidence. Repository selection, licensing, privacy, and reproducibility policy
for those later validations is outside this foundation.

## Implementation Record

### G1: Evaluation Fixture Schema

G1 defines a versioned JSON answer-key format for measuring candidate-selection
quality. It does not run candidate selection, inspect fixture contents, or change
candidate scoring.

Each manifest has this shape:

```json
{
  "schema_version": 1,
  "tasks": [
    {
      "id": "react-auth-form",
      "task": "Fix validation in the sign-in form",
      "fixture_path": "fixtures/react-auth",
      "tags": {
        "stacks": ["frontend"],
        "languages": ["typescript"],
        "frameworks": ["react"]
      },
      "expected_files": {
        "critical": [
          {
            "path": "src/components/SignInForm.tsx",
            "note": "Owns the validation behavior."
          }
        ],
        "useful": [{"path": "src/lib/validation.ts"}],
        "distractor": [],
        "irrelevant": []
      }
    }
  ]
}
```

The four expected-file tiers mean:

- `critical`: needed to perform the task correctly.
- `useful`: relevant supporting context, but not strictly required.
- `distractor`: superficially plausible and useful for measuring false positives.
- `irrelevant`: unrelated fixture content that should not be selected.

All manifest, task, tag, tier, and expected-file fields shown above are required,
except for an expected file's `note`. A note, when present, explains that file's
tier assignment. All four tier arrays must be present but may be empty, including
all four arrays for a task whose answer key is not yet classified.

Task IDs must be unique within a manifest. Tags must be non-empty strings and
must not repeat within one tag category. Unknown fields and tier names are
rejected so schema mistakes fail early.

`fixture_path` is relative to the manifest consumer's fixture base and may be `.`.
Expected-file paths are relative to that fixture root. Paths use forward slashes,
must already be normalized, and cannot be absolute or contain `..`; validation
is lexical and does not require the fixture to exist. A file may appear in
exactly one tier.

Use `load_candidate_evaluation_manifest(path)` to load UTF-8 JSON, or
`validate_candidate_evaluation_manifest(payload)` for an already decoded value.
Both return immutable dataclasses and raise `CandidateEvaluationManifestError`
for schema errors.

### G2: Measurement and Stage Report Foundation

G2 adds a shared immutable `StageReport` for future candidate-evaluation stages.
Each report contains `stage_name`, JSON-ready `inputs`, `outputs`, and `metrics`,
ordered `warnings` and `skipped_items`, `confidence`, `elapsed_ms`, `bytes_read`,
and `files_touched`.

Confidence is one of `unknown`, `low`, `medium`, or `high`. Cost fields are
non-negative; byte and file counts are integers, while elapsed milliseconds may
be an integer or float. Mapping keys are sorted, nested values are copied into
an immutable representation, and `to_dict()` produces a stable shape accepted
by `json.dumps` without a custom encoder. Immutable helpers append warnings or
skipped items and add metrics without modifying the original report.

`elapsed_milliseconds(start_ns, end_ns)` converts monotonic nanosecond readings
to milliseconds. G2 does not calculate candidate-quality metrics or connect
reports to candidate selection; those integrations remain later milestones.

### G3: Fixture Set Foundation

G3 provides five tiny deterministic fixture repositories under
`tests/fixtures/candidate_quality`: `strata_smoke`, `messy_python`,
`messy_react`, `messy_angular`, and `external_style_small`. Each fixture keeps
its G1 manifest separate from its `repo/` inventory root and includes one task
with critical, useful, distractor, and irrelevant expected files.

The fixtures cover Python, React, Angular, Strata-shaped repository
intelligence, and a small external-style library layout. They deliberately
include generic filenames such as `index.ts`, `helpers.py`, `utils.ts`,
`service.ts`, and `api.ts` to exercise ambiguous candidate names in later
milestones.

All fixture content is synthetic and authored for local tests. These are not
clones, samples, or benchmark results from real GitHub repositories. G3 adds no
quality metrics, baseline reports, candidate scoring, probing, or runtime
candidate-selection integration.

### G4: Candidate Quality Metrics

G4 grades an ordered candidate list against one G1 evaluation task. Paths are
normalized to relative forward-slash form, duplicate paths are removed while
preserving their first position, and K is applied after deduplication.

The metrics are:

- `critical_recall_at_k`: critical files selected in the first K divided by all
  expected critical files.
- `useful_coverage_at_k`: useful files selected in the first K divided by all
  expected useful files.
- `distractor_rate_at_k`: distractors selected in the first K divided by the
  number of unique candidates actually evaluated, up to K.
- `missed_critical_count`: expected critical files absent from the first K.
- `context_waste_at_k`: distractor, irrelevant, and unclassified paths in the
  first K divided by the number of unique candidates actually evaluated.

Using the evaluated selection count as the rate denominator means a selector
that returns fewer than K files is measured on what it actually supplied.
Unknown paths are deterministic waste because they consume context without an
answer-key value. An empty critical or useful tier has coverage `1.0` because
nothing required from that tier was missed; a rate with no evaluated candidates
is `0.0`.

Critical recall is prioritized over plain precision because omitting a file
required to perform the task can make the context unusable even when every file
that was selected looks relevant. Waste and distractor rates remain visible as
the counterweight to indiscriminately selecting more files. G4 does not run the
candidate engine or create baseline reports.

### G5: Current Engine Baseline Report

G5 runs the existing `analyze_candidates_for_task` pipeline unchanged for every
G3 manifest task, using the manifest task text and fixture `repo/` as inputs.
The selected paths retain engine rank order and are graded at configurable K by
the G4 metrics.

Each task report contains the fixture name, task ID and text, K, selected paths,
metrics, and a G2 `StageReport`. The stage records files considered, truncation,
ranked outputs, metrics, warnings, elapsed milliseconds, bytes read, and files
touched. `bytes_read` is zero because the current candidate pipeline inventories
paths and metadata without opening content; `files_touched` is the number of
inventory records materialized.

Aggregate output has a fixed report version and engine name followed by all
task reports in sorted fixture and manifest task order. Timing defaults to zero
for reproducible baseline JSON; callers may provide a monotonic nanosecond clock
when observational elapsed time is wanted.

This report is the pre-improvement measurement of the current engine. It does
not change ranking, scoring, frontend signals, inventory behavior, or selection
limits, and it does not implement probes or baseline comparisons.

### G6: Mixed Probe Pool Design

G6 builds a deterministic, metadata-only pool for later probing. The obvious
lane accepts ranked paths from the unchanged current engine. The independent
rescue lane examines inventory paths for framework and configuration anchors,
files adjacent to those anchors, task-matching folder segments, task-relevant
roles, generic structural filenames, and recognizable source-directory shapes.
It never consults the current candidate score.

Each entry records its path, ordered sources and reasons, obvious and rescue
rank hints, and lane-membership flags. A path found by both lanes appears once
with merged provenance. Confidence is intentionally absent: structural rank
hints organize the pool but are not additive relevance scores.

The initial policy caps the combined pool at 40 entries, with at most 20 obvious
and 20 rescue candidates and at most 5 entries per directory. Obvious entries
retain engine order; rescue entries use fixed structural priority followed by a
lexical path tie-breaker. These values are bounded starting points rather than
permanent quality thresholds.

Pool construction consumes existing `InventoryRecord` metadata and relative
paths only. It does not open, read, or stat files, and it does not perform
content probing, change candidate selection, or compare against the baseline.

### G7: Probe Scoring Contract

G7 defines normalized components and score math for future bounded probes. Each
result records a relative path, cheap relevance, probe relevance, structural
relevance, normalized cost, final score, confidence, and the applied weights.
All four input components must be finite values from `0.0` through `1.0`.

The default contract is:

```text
final_score =
    0.35 * cheap_relevance
  + 0.30 * probe_relevance
  + 0.20 * structural_relevance
  - 0.15 * normalized_cost
```

The immutable default weights are cheap `0.35`, probe `0.30`, structural
`0.20`, and cost `0.15`. Custom weights must each be normalized, must include
some relevance weight, and must sum to `1.0`; the cost weight is always applied
as a subtraction. Because cost is a penalty, final scores themselves may range
from `-0.15` to `0.85` under the defaults.

Confidence uses the G2 values `unknown`, `low`, `medium`, and `high`. It is
metadata only: it is neither a score component nor a sorting boost. Results sort
by descending final score with normalized path and component tie-breakers and
convert directly to stable JSON-ready dictionaries. G7 performs no probing,
filesystem access, candidate selection, or baseline comparison.

### G8: Bounded Content Probe

G8 reads one bounded leading content window from each eligible mixed-pool file
and returns normalized `probe_relevance` for the G7 contract. The window may
surface task terms, import/export declarations, class or function signatures,
top comments, route markers, and obvious framework declarations. It does not
parse full files, trace imports, call models, or rerank product candidates.

The experimental default policy allows at most 20 open attempts, 4 KiB per
file, 32 KiB total, and files no larger than 256 KiB. All caps are explicit and
validated. Paths are normalized and prevalidated before any read, resolved
inside the supplied root, and read once in binary mode with a bounded size.

Missing, oversized, non-regular, outside-root, unreadable, binary, and non-UTF-8
files produce deterministic skipped results with zero relevance. Binary and
non-UTF-8 windows still count bytes already read. Paths after the file or total
byte cap are marked skipped without filesystem access.

Each result records path, relevance, evidence, lightweight signals, confidence,
bytes read, and an optional skipped reason. Confidence is derived after the
normalized relevance value and remains metadata only. The aggregate G2
`StageReport` records elapsed milliseconds, total bytes read, paths inspected,
warnings, skipped items, result counts, and average probe relevance. Timing is
zero by default for reproducible output and may use an injected monotonic clock.

### G9: Probe vs Baseline Evaluation

G9 compares three library-only strategies across every G3 task:

- `baseline`: the unchanged current engine output measured by G5.
- `mixed_pool`: G6 obvious and rescue ordering without content reads.
- `mixed_pool_probe`: the same pool ranked with G7 after the bounded G8 probe.

The probe strategy maps existing evidence into normalized G7 components. Cheap
relevance decays from obvious-lane rank, structural relevance is the fraction
of six rescue signal types present, probe relevance comes directly from G8, and
normalized cost is bytes read divided by the per-file byte cap. Confidence is
passed through as metadata and has no effect on the score or tie-breaking.

Every task-strategy row reports ranked paths at K, all five G4 quality metrics,
notes relative to baseline, and a G2 stage report containing elapsed time,
bytes read, files touched, warnings, and skipped items. Aggregate summaries
report average critical recall, total missed critical files, average useful
coverage, average distractor rate, average context waste, total bytes read, and
total files touched for each strategy.

The probe-cost assessment compares `mixed_pool_probe` with `mixed_pool`, which
isolates incremental read cost. The probe earns its cost when it improves
critical recall or reduces missed critical files, or when critical performance
is unchanged and useful coverage improves without increasing context waste.
The raw quality and cost values remain authoritative even when that initial rule
returns false.

G9 is evidence gathering only. It does not change product candidate ranking,
selection, CLI behavior, or workflow behavior, and it does not add deeper
tracing, representations, or model calls.

### G10: Final Policy and Roadmap Contract

G10 designates the Contract Surface, Locked Part G Policies, and Downstream
Dependencies sections above as the authoritative handoff. The G1–G9 sections
remain the implementation record and detailed rationale. Future work changes a
Part G contract only through an explicit schema/default version decision and
corresponding fixture, contract, quality, and cost tests.
