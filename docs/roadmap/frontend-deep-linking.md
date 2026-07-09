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

Later batches may populate the J1 contract without changing its public shape:

1. J2 Angular component-template-style linking
2. J3 Angular route/lazy route linking
3. J4 React component/hook/API linking
4. J5 Internal library usage inference from templates/code
5. J6 Module Federation/custom element detection
6. J7 Frontend linking evaluation/docs

These later batches are intentionally not implemented by J1.

## Boundaries

J1 does not implement Angular template parsing, Angular route tracing, React
component/hook/API tracing, module federation detection, custom element
detection, file scanning, `package.json` reading, `tsconfig` parsing, workspace
intelligence, adapter-specific prompt files, generated context artifacts, model
calls, or daemon/background processes.
