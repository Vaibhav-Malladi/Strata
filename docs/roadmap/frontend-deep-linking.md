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
J2-J6 now begin that population work for Angular, React, internal-library, and
frontend boundary metadata:

1. J2 Angular component-template-style linking
2. J3 Angular route/lazy route linking
3. J4 React component/hook/API linking
4. J5 Internal library usage inference from templates/code
5. J6 Module Federation/custom element detection
6. J7 Frontend linking evaluation/docs

J7 remains intentionally outside J6.

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

## J3: Angular Route/Lazy Route Linking

J3 adds a small, stdlib-only helper for one supplied Angular route/config source
string and path. It infers `component_route` relationships for direct
`component: SomeComponent` route metadata and `route_lazy_target` relationships
for common lazy route forms:

- `loadComponent: () => import('./path').then(m => m.SomeComponent)`
- `loadChildren: () => import('./path').then(m => m.SomeModule)`
- nested `children` arrays within the supplied source string

Lazy import targets are resolved only when they are relative to the route/config
file directory. The imported symbol is recorded as `target_symbol` when the
common `.then(m => m.Symbol)` form is present. `redirectTo` routes do not create
component or lazy-target relationships. Malformed route metadata, absolute lazy
imports, and traversal outside the repository degrade to low-confidence
relationship records with warnings rather than crashing.

J3 does not implement full TypeScript parsing, route graph traversal across
many files, repository scanning, `tsconfig` parsing, `package.json` reading,
component-template-style linking, React linking, internal library usage
inference, module federation detection, custom element detection, workspace
intelligence, Part I artifact changes, or generated `.aidc/context` artifacts.

## J4: React Component/Hook/API Linking

J4 adds a small, stdlib-only helper for one supplied React/JS/TS source string
and path. It infers React relationships for conservative source-text signals:

- uppercase JSX tags such as `<UserCard />` become `component_child_component`
- custom hook calls such as `useOrders()` become `hook_component`
- API/client-like calls such as `api.get(...)`, `OrdersClient(...)`, or
  `fetch(...)` become `component_api_client` or `hook_api_client`
- `React.lazy(() => import('./Feature'))` and `lazy(() => import('./Feature'))`
  become `react_route_component`

Lazy import targets are resolved only when they are relative to the source file
directory. Unsafe lazy imports, absolute lazy imports, traversal outside the
repository, or malformed lazy metadata degrade to low-confidence relationship
records with warnings rather than crashing. Lowercase HTML tags are ignored.

J4 does not implement Babel or TypeScript parsing, route graph traversal,
repository scanning, `tsconfig` parsing, `package.json` reading, Angular
linking, internal library usage inference, module federation detection, custom
element detection, workspace intelligence, Part I artifact changes, or
generated `.aidc/context` artifacts.

## J5: Internal Library Usage Inference

J5 adds a small, stdlib-only helper for one supplied frontend source/template
string and path plus optional known internal packages, known internal symbols,
and framework hints. It emits `internal_library_usage` relationships for
conservative consuming-code signals:

- imports from known internal packages
- private-looking imports such as `@company/*`, `@org/*`, `@internal/*`, or
  `@enterprise/*`
- Angular template selectors, attribute directives, pipes, and injected
  services matching known internal symbols
- React JSX components, hooks, and API/client/service symbols matching known
  internal symbols
- low-confidence company-prefix selector guesses when no known symbol is
  supplied

Explicit imports from supplied known internal packages are high confidence.
Known symbol usages in templates/code are medium confidence. Prefix-only
private guesses are low confidence and carry warnings asking later stages to
confirm with Bridge/internal-library resolution.

J5 does not rediscover internal libraries, scan `node_modules`, read
`package.json`, parse `tsconfig`, scan repositories, implement module federation
or custom element detection, perform workspace intelligence, update Part I
canonical artifacts, or create generated `.aidc/context` artifacts.

## J6: Module Federation / Custom Element Detection

J6 adds a small, stdlib-only helper for one supplied source/config/template
string and path. It emits boundary relationships for conservative signals:

- `module_federation_remote` from `remotes` object/array config
- `module_federation_remote` from `exposes` object config
- `module_federation_remote` from `loadRemoteModule(...)`
- `module_federation_remote` from federated-looking dynamic imports such as
  `import('orders/Module')`
- `module_federation_remote` from `remoteEntry.js` literals
- `custom_element_usage` from `customElements.define(...)`
- `custom_element_usage` from `document.createElement('custom-tag')`
- low-confidence `custom_element_usage` from hyphenated template tags

Explicit Module Federation config and `customElements.define(...)` are high
confidence. Federated-looking dynamic imports and standalone `remoteEntry.js`
literals are medium confidence. Hyphenated template tags without a definition
are low confidence and carry warnings because ownership is not proven.

J6 does not perform cross-repo scanning, read webpack config files from disk,
read `package.json`, parse `tsconfig`, scan `node_modules`, look up workspace
configuration, trace user journeys, update Part I canonical artifacts, or
create generated `.aidc/context` artifacts.

## Boundaries

J1 does not implement Angular template parsing, Angular route tracing, React
component/hook/API tracing, module federation detection, custom element
detection, file scanning, `package.json` reading, `tsconfig` parsing, workspace
intelligence, adapter-specific prompt files, generated context artifacts, model
calls, or daemon/background processes.
