# Candidate Evaluation and Quality Foundation

## G1: Evaluation Fixture Schema

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
Expected-file
paths are relative to that fixture root. Paths use forward slashes, must already
be normalized, and cannot be absolute or contain `..`; validation is lexical and
does not require the fixture to exist. A file may appear in exactly one tier.

Use `load_candidate_evaluation_manifest(path)` to load UTF-8 JSON, or
`validate_candidate_evaluation_manifest(payload)` for an already decoded value.
Both return immutable dataclasses and raise `CandidateEvaluationManifestError`
for schema errors.

## G2: Measurement and Stage Report Foundation

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

## G3: Fixture Set Foundation

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

## G4: Candidate Quality Metrics

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

## G5: Current Engine Baseline Report

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

## G6: Mixed Probe Pool Design

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

## G7: Probe Scoring Contract

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

## G8: Bounded Content Probe

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

## G9: Probe vs Baseline Evaluation

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
