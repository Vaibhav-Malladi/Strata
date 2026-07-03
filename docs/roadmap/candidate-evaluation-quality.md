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
