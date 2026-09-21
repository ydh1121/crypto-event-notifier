# CRYPTO UI FOUNDATION CONTRACT — V18

Status: ACTIVE FOUNDATION CONTRACT  
Work Order: CRYPTO-WO-20260921-002  
Authority: user instruction → AGENTS.md → DESIGN.md → TASTES.md → MODULAR_ARCHITECTURE.md → this document

## 1. Purpose

This contract reduces propagation debt before any broad page redesign. It does not change trading logic, strategy semantics, PAPER behavior, data contracts, holdings semantics, or live-trading boundaries.

## 2. Ownership layers

1. `tokens.css` owns primitive and semantic UI geometry: control height, input height, touch height, radius, gaps, panel radius, workspace gap, rail bounds, and focus ring.
2. `shell.css` owns global shell geometry and top-level navigation chrome.
3. `components.css` owns reusable controls and compositions.
4. Page styles own page-specific content only.
5. Compatibility/repair layers may preserve existing pages but must not introduce new foundational tokens or duplicate canonical control geometry.
6. Legacy compatibility layers must not flatten page-owned responsive grids at desktop widths. Page/component owners retain their declared desktop/tablet/mobile grid responsibilities.

New page-local `!important` rules for shared controls require evidence that the shared component cannot express the need.

## 3. Canonical tokens

- `--control-h`
- `--control-input-h`
- `--control-touch-h`
- `--control-radius`
- `--control-gap`
- `--panel-radius`
- `--section-gap`
- `--workspace-gap`
- `--master-rail-min`
- `--master-rail-max`
- `--focus-ring`

Do not recreate these values under generation-specific names.

## 4. Canonical component families

Current shared selectors remain supported. New migrations should converge on:

- `.ui-toolbar`
- `.ui-master-detail`
- `.ui-master-rail`
- `.ui-detail-pane`
- `.ui-fact-strip`
- `.ui-disclosure`
- `.ui-action`

Existing stable exemplars are migrated additively in later bounded waves. Do not perform a big-bang class rename.

## 5. Explicit lifecycle

DOM enhancement must be driven by the owning render path or explicit `ui:refresh` events.

Forbidden:
- document/body/documentElement subtree MutationObserver loops for normal page decoration
- self-triggering DOM rewrite observers
- polling merely to discover whether a component was rendered

Allowed:
- bounded data polling owned by data/runtime modules
- component-local observers only when the browser primitive itself requires observation and the scope/reason is documented
- explicit render, route, store, or `ui:refresh` lifecycle events

`rail-controls-v16.js` is root-scoped to `#pageRoot` and must not install a broad MutationObserver.

## 6. Responsive and accessibility baseline

- native controls and semantic landmarks first
- visible `:focus-visible`
- coarse-pointer form controls must not trigger iOS focus zoom; 16px minimum
- buttons use `touch-action: manipulation` and retain clear pressed/focus feedback
- 44px touch geometry is the target for compact/mobile surfaces where controls are primary
- preserve zoom; never disable user scaling
- honor `prefers-reduced-motion`
- preserve selected object, filter, sort, scroll, and focus during live polling/reader-mode transitions
- sticky shell must reserve browser scroll/focus visibility via `scroll-padding-top` derived from `--shell-header-offset`; focused/anchored content must not land underneath the header stack
- `viewport-fit=cover` requires shell/auth/journey ownership of `safe-area-inset-*`; compact primary controls use `--control-touch-h` and must remain usable at 360/390/430px without disabling native zoom

## 7. Stable exemplar preservation

Do not regress without explicit evidence:
- Strategy V5 master/detail workspace
- Records user/system audience split
- Research master/detail + scoped live patch
- Assets V17 hero/facts/editor handoff
- ui-continuity.js
- scoped V16 live-patch ownership
- viewport-handoff-v4 mobile return pattern

## 8. Compatibility debt guard

The V18 regression checker caps the known late-override debt at the WO-001 audit baseline. Refactoring may lower the counts. Increasing them requires an explicit contract update with rationale.

The foundation wave intentionally does not delete legacy compatibility CSS until representative desktop/tablet/phone visual QA proves the declarations can be retired safely.
