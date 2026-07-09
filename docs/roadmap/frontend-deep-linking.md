# Frontend Deep Linking

Part J improves Strata's understanding of how frontend files connect while
preserving Part I as the token firewall. Part J discovers and classifies
relationships; Part I decides how any populated relationship is represented in
canonical context artifacts.

## J1: Frontend Relationship Contract

J1 is contract-only. It defines stable relationship type, framework, and
confidence constants plus an immutable JSON-ready relationship model and
deterministic sorting/grouping helpers.

The J1 contract can represent Angular, React, generic frontend, internal
library usage, module federation, and custom element relationships. It includes
placeholder vocabularies for those producers, but it does not parse, scan,
trace, detect, or read frontend files.

Relationship evidence is repository-derived. If a later stage renders it into
prompt context, it must be treated as untrusted repository content and kept
behind the appropriate Part I trust boundary.

## Later J Batches

Later batches may populate the J1 contract without changing its public shape.
J2 now begins that population work for one Angular component at a time:

1. J2 Angular component-template-style linking
2. J3 Angular route/lazy route linking
3. J4 React component/hook/API linking
4. J5 Internal library usage inference from templates/code
5. J6 Module Federation/custom element detection
6. J7 Frontend linking evaluation/docs

J3-J7 remain intentionally outside J2.

## J2: Angular Component-Template-Style Linking

J2 adds a small, stdlib-only helper for one supplied Angular component source
string and path. It infers `component_template` and `component_style`
relationships for common component metadata:

- `templateUrl`
- `styleUrl`
- `styleUrls`
- inline `template`
- inline `styles`

External template/style targets are resolved only when they are relative to the
component file directory. Inline metadata is represented with a target symbol
such as `inline template` or `inline styles` instead of a target path. Malformed
metadata, absolute targets, and traversal outside the repository degrade to
low-confidence relationship records with warnings rather than crashing.

J2 does not scan repositories, read target files, parse `tsconfig`, read
`package.json`, trace Angular routes, implement React linking, infer internal
library usage, detect module federation, detect custom elements, update Part I
canonical artifacts, or create generated `.aidc/context` artifacts.

## Boundaries

J1 does not implement Angular template parsing, Angular route tracing, React
component/hook/API tracing, module federation detection, custom element
detection, file scanning, `package.json` reading, `tsconfig` parsing, workspace
intelligence, adapter-specific prompt files, generated context artifacts, model
calls, or daemon/background processes.
