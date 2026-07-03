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
