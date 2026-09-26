# Dashboard v1 handoff

### Current — manual planning package verified and delivered; fresh-event reactions next

- **State: PACKAGE_VERIFIED / ACTUAL_PC_APPLICATION_PENDING / F04_NEXT.** Source e392f220b518b9da9f910bbbec94a813cb9c1a86 is committed on agent/crypto-product-data-recovery-20260921. The coding environment recovered without losing the preserved source. Planning, manual execution comparison and closed-holding history are packaged and verified; actual-PC application and visual acceptance remain separate.
- Plans persist by exact exchange+market+KRW+experiment in the existing separate holdings journal. The first explicit save makes a verified SQLite backup before additive tables. Legacy holdings, legacy plans/fills and PAPER data remain unchanged. Revision checks reject concurrent overwrites; request IDs prevent duplicate saves and fills. Generic review remains read-only; only the configured Viewer opts in.
- Manual records use actual paid fees, average-cost accounting and partial sells. Invalid/blank fees and overselling are rejected. Cancellation appends an audit event and cannot invalidate dependent sales. Comparison uses completed cycles that both open and close within the same real-record window, with the same coin and strategy; no aggregate performance substitution.
- The UI restores saved plans on restart, protects current inputs during delayed reads/polling/errors, and separates plan and manual-record tabs. Closed holdings remain selectable under 매도 완료, including when every holding is closed. Saved plans and manual journals can be reopened and records corrected without modifying the canonical zero quantity.
- Validation: the existing 56 distinct affected tests passed before the outage. After the archive change, reran only affected Python holdings/HTTP tests (12 passed) and holdings/session JS/DOM (16 passed); added archive reopen/correction, all-closed selection and zero/blank scope assertions. Prior TypeScript/compile results retained; changed Python compile and diff checks passed. Browser visual acceptance and actual-PC new save are not established.
- Delivered CRYPTO_STRATEGY_REVIEW_e392f22.zip, 46 files / 106,741 bytes, SHA256 623221d72949edb3bae5c49ff7633dc695c720068dbc88f7403bf408148c236b; manifest SHA256 f2f1d858c684b40c0c263702443043ee1b4d52ccadac6d4e6a03288559faeefa. Saved as version 9 of the existing Viewer artifact. Both launchers retain owner-confirmed Bithumb; RUN_REVIEW explicitly enables local planning, while RUN_CHECK remains read-only.
- Extracted-package verification passed: stdlib Python imports; actual local HTTP save/restart/restore; duplicate-fill and stale-write rejection; first-save verified backup; unchanged PAPER hash and unchanged legacy holdings/plans; closed archive reopen; all 22 JS modules resolve. The extracted JS renders the same synthetic API readback: manual realized PnL 48, paid fees 2, one completed manual cycle and two eligible PAPER cycles. These are fixture values, not private portfolio amounts or actual-PC evidence. Browser visual acceptance is not claimed.
- Apply by leaving collectors running, closing only the old review window, extracting the new folder and running RUN_REVIEW.cmd. No collector restart, Git install or canonical DB replacement is required. First explicit save creates the verified holdings-journal backup.
- Then continue F04/P0: one fresh actual event, coin/BTC/ETH baseline and all four horizons, followed by reaction sub-tabs and compact numeric tables. Preserve the expanded F01–F31 requirements; do not restart an unrelated CSS audit.
- Latest actual Windows evidence and previously delivered a330b8b remain recorded below. No new Windows runtime inspection, collector restart, strategy/PAPER rule change, production deployment, primary merge or order activation.

## Previous applied checkpoint — CRYPTO-WO-20260921-RECOVERY-001

**Status: BITHUMB_HOLDINGS_APPLIED / FOUR_HOLDINGS_VALUED. Actual PC verified Viewer a330b8b with all four holdings resolved to Bithumb and all four KRW valuations visible. B3 PAPER account still reconciles eight fills. ETH per-unit detail, explicit public refresh connectivity and final design acceptance are not established by these attachments.**
This block supersedes older visual-acceptance and BLOCKED_LOCAL_EVIDENCE checkpoints below.

### Actual configured holdings application — 2026-09-25 16:52 KST

- Read the new `CRYPTO_B3_REVIEW_RESULT.json` locally: 55,617 bytes, SHA256 `551cb36ec10ea1c83fc60b6e47c95badad6857a4ccdeb172baebebacde7fdb37`; viewed both `image(20260925-075323).png` and `image(20260925-075330).png`. The application-generated missing-image message was stale: both local images were present and readable. Do not upload private attachments or real holding amounts to the repository/package.
- Actual observation 16:52:03–16:52:39 KST verifies Viewer source `a330b8b34db5cdd3a622d4954ece0484462a5a95`, manifest SHA256 `358935be0f69162844451cca6ea20a7a1c0ceffb1eea7927dda1f6dbbed5ca4f`, integrity verified. PAPER DB is 3,331,334,144 bytes. No new actual-PC Git reading; collector source remains last verified 4af291d.
- Configured `confirmed_exchange=bithumb` is applied. Separate project-setting holdings journal reports four active / one closed, four complete identities, three KRW-plannable, zero resolved unknown exchanges, two raw stored unknown exchanges and one non-KRW holding. Both SLX and UP now display Bithumb. The screenshot shows all four KRW holding values and their displayed sum matches the total; B3 quantity/average/value/PnL remain arithmetically consistent. This is actual PC evidence, not a fixture-only claim.
- ETH is not selected in either screenshot. Its list value is a total holding valuation, not the per-unit ETH price. The blank total KRW PnL remains deliberate because historical BTC acquisition FX is unknown. No success/failure status for an explicit public-price refresh is shown, and the report contains no public quote receipt. Do not upgrade this evidence to native BTC-pair API success, an observed ETH detail view, or final user design approval.
- B3/aggressive still reconciles eight fills / three completed trades / two wins with an open position; no new B3 fill is proven. PAPER account equity, cash, position value and unrealized PnL agree with the screen at the saved quote. Independent actual holdings are not substituted into the PAPER account. Three closes do not prove strategy superiority.
- PAPER/memory and the four sampled BTC/ETH trade-flow streams advanced during the observation. Lab clocks remained unchanged over a window shorter than its next due time; its last cycle processed 286 source rows and made zero trades. Last OHLCV cycle wrote 3,951 rows for 16 markets, consecutive deferrals zero. Intelligence last cycle had zero source/response failures and zero new reactions, 310 already captured, 8,400 missing baselines / 590 missing targets among 8,990 due attempts; no claim of full event coverage. Host/research/PAPER/flow/forward owner checks match and observed children were running; historical exits are not new failures.
- This unit records actual application and limits only. No source behavior change, new package, test repetition, production publication, DB mutation or process restart. Keep the delivered a330b8b Viewer (existing artifact version 8). Prior 35 affected tests and extracted-package verification remain the source validation record.
- Next implementation scope remains durable real-trade planning and manual small-trade ledger comparison, reusing canonical fee/holdings identity logic; canonical holdings edit/publish integration is still separate. Continue event baseline/response coverage from actual new samples. The unobserved ETH detail/public refresh must stay unverified until corresponding evidence exists.

### Owner-confirmed Bithumb holdings and KRW price display — 2026-09-25

- User explicitly stated that all actual holdings belong to Bithumb and ETH/BTC must show a KRW-converted price. This is new authoritative portfolio input, not an inferred exchange fallback. Add an explicit `--holdings-exchange bithumb` configuration to this user's packaged launchers; generic source defaults still use stored exchange identity. Preserve stored exchange and mark the resolved source as owner-confirmed. Apply only to real-holdings reads, never PAPER exchange identities. Canonical holdings quantities, average prices, zero rows and raw exchange columns are not mutated by this read-only package.
- Read `CRYPTO_B3_REVIEW_RESULT(5).json` locally, 55,463 bytes, SHA256 `61bed0e0ecb01176de46d0e424f471a695e8e8b71fe4a16caeb6f0108757677c`, and `a08a679d-478b-4d3a-ae03-bda98ec8d46b.png`. Verified Viewer source c85f545787b67a9529d7122b13d7cd413ba3dd0b. Actual observation 11:53:15–11:53:49 KST; PAPER DB 3,196,620,800 bytes. Separate holdings DB: four active / one closed, two stored identities complete / two exchange fields unresolved, one non-KRW record. No private real-holding amounts or report files are committed/uploaded.
- Screenshot confirms public-quote partial failure and only one valued holding in the previous version. The report contains no HTTP/transport cause for the price action. Do not claim BTC-ETH is delisted, an exchange outage, or a known PC TLS/clock failure. Execution-environment public quote probing also could not establish a live response. New failure metadata is bounded to safe reason/status fields, without response bodies/credentials.
- PAPER account/ledger now reconcile eight fills, three closed trades, two wins and an open position. PAPER/memory/lab account/lab metrics/trade-flow clocks advanced in the paired observation. OHLCV/events/responses/archive clocks were unchanged within that short interval; this is not proof of stopped collectors. Last verified collector source remains 4af291d; the report is a Viewer revision, not fresh PC Git evidence.
- Display ETH/BTC's per-unit KRW quote prominently, separately from quantity-times-price holding value. Prefer actual BTC-ETH price times the same exchange's BTC/KRW quote. If that conversion is unavailable or stale while a current same-exchange KRW-ETH quote exists, show it under the distinct label `빗썸 원화마켓 평가가`. Do not synthesize a BTC pair price/return or historical KRW purchase cost. Native BTC cost/PnL remain separate; unknown historical acquisition FX still prevents an invented total KRW PnL.
- Both native and alternative KRW evaluation use exact exchange and source clocks. A foreign exchange's KRW price is never borrowed. Unknown/stale quote evidence stays visible. Split public KRW and BTC requests so a BTC-pair HTTP failure cannot discard valid KRW prices; include the same asset's KRW quote as an explicit valuation source. Stop subsequent groups after connection/TLS/timeout/rate-limit errors. Preserve cached prices and original clocks. No credentials, orders, data mutation, consumer activation, collector restart or production deploy.
- Verification: 24 distinct affected Python tests and 11 holdings JS/DOM tests passed; TypeScript, Python compile and diff checks passed. Covered owner-declared identity resolution with unchanged journal hashes and unchanged default behavior, native conversion vs direct same-exchange KRW basis, per-unit vs total values, missing/future/stale/foreign prices, partial HTTP batch failure, retained source clocks, fee-aware split plans and UI continuity. Configured package verification is complete (details below). Prior localhost-browser policy block was not bypassed.
- Package readback complete: `CRYPTO_STRATEGY_REVIEW_a330b8b.zip`, source `a330b8b34db5cdd3a622d4954ece0484462a5a95`, 41 files / 92,210 bytes, SHA256 `aff6cf5286e894828c077a693f51f492f62604b022acadacc0aff687a425abea`. Saved as version 8 of the existing Viewer artifact. Both launchers explicitly pass `--holdings-exchange bithumb`. Extracted stdlib Python verifies the manifest and all four synthetic holdings, with separate PAPER/holdings DB hashes unchanged. The configured CLI report resolves four identities while retaining two raw missing exchanges. The same Python output renders per-unit native-converted and direct-KRW ETH prices in extracted JS; SLX/UP request only Bithumb strategy scope. All 19 JS modules and both stylesheets resolve. This verifies package behavior, not actual-PC quote connectivity or visual acceptance. No collector restart is required.
- Next: open the configured read-only Viewer and verify the actual Bithumb holdings list and ETH KRW price/basis. The package does not claim canonical exchange columns were rewritten. Integration with the existing canonical holdings editing/publishing path, durable plans and manual small-real-trade comparison remain separate work.

### Earlier actual holdings evidence and native-quote planning — 2026-09-25

- Read `CRYPTO_B3_REVIEW_RESULT(4).json` locally (53,524 bytes, SHA256 `9fcf6af640e1ca76ad608bddce54fa2711690c8dc8eca1a3573f27a979b27753`) and the actual holdings screenshot `0cc6cc6f-48ca-46b0-bd70-532b4aa34b74.png`. Viewer source bc58b2785614c5aee45f2ca32523c12bbad83b59 / integrity verified. Observation: September 25 00:32:12–00:32:45 KST. PAPER DB 3,081,179,136 bytes; no new PC Git observation. Collector source remains last verified 4af291d, not this Viewer revision.
- Actual holdings journal resolves from project setting to `b3_trader/data/crypto_trader.sqlite3`: four active, one closed record. B3 real position/average/value/PnL agree arithmetically with the screenshot; the flat PAPER balance was not substituted. Private holding quantities/amounts and the input report are not copied into repository/package. Screenshot is evidence of connection, not final UI acceptance.
- Only one of four holdings was valued: ETH is Bithumb BTC market, while the old input price set covers KRW adaptive signals; SLX/UP have no exchange. Old `identity_complete_count=1` actually counted KRW-plannable holdings; fixed to distinguish complete identity, KRW planning, unknown exchange and non-KRW counts. Missing exchange is never guessed from ticker.
- PAPER/memory and all four sampled BTC/ETH streams advanced across 33 seconds. OHLCV last cycle wrote 4,027 rows for 16 markets, consecutive deferrals zero. Intelligence last cycle inserted one response using one archived baseline and target, failures zero; the inserted coin/horizon is not identified. Lab clocks were unchanged inside a shorter-than-cadence observation and do not prove failure. Supervisor owner PIDs/start counts match the previous report, all observed running. B3/aggressive still reconciles six fills / three closes / two wins / flat. Three trades do not establish validated superiority.
- Added an explicit local `현재가 새로고침` action using the same public /v1/ticker contract as existing exchange clients, with a stdlib-only read adapter. Only allowlisted public market codes are requested for valid active holdings with a known exchange; no quantity, average, credentials or DB bytes leave the PC. Reports/startup/automatic UI polling make no external requests. Fixed HTTPS hosts, no redirects, size/time limits, 15-second request throttling, exact response-market and trade-clock validation. Old quotes retain their original clocks on failure. Fixture mode blocks external quotes.
- BTC-market valuation uses its actual native pair price plus the same exchange's BTC/KRW price. No ETH/KRW ratio synthesis or cross-exchange fallback. Display native price/PnL separately from current KRW valuation. Without acquisition-time FX, total KRW PnL remains unknown even when valuation coverage becomes complete. Unknown/stale/zero stay distinct; all canonical databases remain read-only.
- Real holdings show a numeric TP reference derived from their own stored average and the selected scoped strategy rule. Buy-price and TP-price imports are independent: sell import needs no buy budget, preserves entered buy rounds and computes TP from the post-buy average; buy import preserves edited exits. Existing fee/cost calculation remains canonical. Empty sale plans show no realized-PnL estimate. Price refresh preserves per-holding/strategy drafts and focus. No strategy/PAPER semantics, holdings mutations, process restarts or production deploys.
- Verification: 21 affected Python tests and 26 distinct JS/API/DOM tests passed; TypeScript, compile, diff and existing V18/V16 foundation checks passed. Tests cover separate exact identities, native conversion/unknown historical FX, invalid/future/duplicate quotes, throttling/failure clock retention, explicit-only HTTP reads, cross-site rejection, unchanged database hashes, split imports, fee/quantity conservation and polling continuity. The previous localhost browser policy block was not bypassed. New direct public quote access on the Windows PC and final visual acceptance remain unverified. Extracted-package readback is recorded below.
- Package readback complete: `CRYPTO_STRATEGY_REVIEW_c85f545.zip`, source `c85f545787b67a9529d7122b13d7cd413ba3dd0b`, 41 files / 90,764 bytes, SHA256 `222309ffd28ef84bef08156078e5cf9ea16bd25682a0b683c913eebee0c80ba5`. Extracted Python -B -S verifies the manifest and native valuation using separate synthetic journals with unchanged DB hashes; the same readback renders in extracted JS and imports an independent TP plan with canonical fees. All 19 resolved JS modules and both stylesheets are included. Saved as version 7 of the existing Viewer artifact identity. Actual-PC quote connectivity and visual acceptance for this version remain pending; no collector restart is required.
- Next: use the new local Viewer to read actual BTC-market quotes and check the independent TP flow; resolve unknown holding exchange through the existing authorized holdings workflow rather than guessing or activating its consumer. Continue coin evidence/event coverage and the eventual manual small-real-trade comparison; this increment is not completion of the full product.

### Earlier actual event evidence and holdings planning — 2026-09-24

- Read local attachments `CRYPTO_B3_REVIEW_RESULT(3).json` (53,295 bytes, SHA256 `7f82fb435b0407c64aa2c3925ac7c9168666e7280fb6a5bd141dbc1986253255`) and `195368af-dce6-4df5-a3f0-6d91addc05f9.png`. Report confirms Viewer d60449c / verified manifest. Observation: 17:20:42–17:21:18 KST. PAPER DB remains 3,081,179,136 bytes. No new PC Git observation; collector source remains last verified 4af291d.
- PAPER, memory, lab account/metrics and all four sampled BTC/ETH streams advanced. Latest OHLCV receipt 17:15:57 KST; last cycle wrote 4,054 rows for 16 markets. Last intelligence cycle 17:10:04 KST inserted one response using one archived baseline and one archived target (source/response failures 0). This establishes actual archive consumption; the report does not identify that new response's coin/horizon. No inference of all-market coverage.
- Host/research/PAPER/flow/forward owners match. Research/PAPER started once; forward started twice and flow four times, with earlier code-1 exits and subsequent owned restarts. All were running during this observation. Permission-denied/crash categories lack log bodies and do not establish their root cause. Do not claim uninterrupted uptime or a currently dead collector. No restart is needed for the new Viewer.
- Screenshot and JSON agree on the September 24 01:00 KST SEC event: B3 baseline missing, preserved 15m target 1.03 at 01:16:07 and 1h target 1.032 at 02:00:39. BTC/ETH have stored 15m/1h/4h returns; 1d was not yet due. B3 relative returns and zero-sample history correctly remain missing. The precise reason that B3 baseline was not captured is not established. The screen is observed, not a user-approved final design.
- B3/aggressive still reconciles six fills / three closes / two wins / zero position; PAPER cash 10,348,855.81 and realized +348,855.81 KRW. Account/source clocks 17:18:42 / 17:17:54 KST. Do not call three completed trades validated superiority.
- Added `holdings_review.py`: opens the existing separate manual journal with SQLite mode=ro/query_only, reuses canonical holding-market identity helpers, never instantiates a writing store. Resolves explicit path, B3_JOURNAL_DB environment/project setting, or canonical crypto_trader.sqlite3 default; ambiguous configuration is not a fallback to PAPER. Missing DB/schema/read failure remains distinct from an empty portfolio; zero closeout rows remain stored. Prices require exact exchange/API market/quote. Unknown/stale prices and incomplete totals stay explicit.
- New local `실전 계획` tab connects real holdings → scoped strategy comparisons → exact strategy ledger → fee-aware split planning. Reuses existing tradingCost/calculatePlan. Imports reference entry prices and relative budget allocation into the user's total budget; never imports PAPER balance/quantity/average. TP uses the user's calculated average and the chosen strategy's TP percentage. Existing average is retained; new fees apply only to planned trades. Drafts are per holding/strategy and survive polling/navigation while open; fresh holding updates require explicit start-value reload. Full 100% sale now consumes exact remaining quantity rather than leaving floating-point dust. No strategy/PAPER rule change.
- Verification: 22 affected Python tests + 22 distinct JS/API/DOM tests passed; TypeScript, Python compile, diff whitespace and existing V18/V16 foundation checks passed. Tests cover separate journals, identity/quote isolation, missing/zero/stale data, read-only HTTP, report-file protection, budget/fee conservation, split-sell limits, exact ledger navigation and polling continuity. Fixtures only for the new holdings flow. The supplied report contains no actual manual-holdings rows; no real holdings balance or new-screen visual acceptance is claimed. Prior localhost browser policy limitation was not bypassed.

- Package verification complete: `CRYPTO_STRATEGY_REVIEW_bc58b27.zip`, source `bc58b2785614c5aee45f2ca32523c12bbad83b59`, 40 files / 86,609 bytes, SHA256 `73cdc72af5862f5a881eee5326a7e23e40e39fe4f9c67e422bc3cf97b9d819d1`. Extracted Python -B -S verifies manifest and reads two separate temporary DBs with both hashes unchanged; extracted JS renders those same holdings and fee-inclusive averages. Independent esbuild dependency resolution confirms every required module is included. Fixed the packager's old broad regex that misread an HTML class ending in -import as a dependency. No collector/recovery code runs in this Viewer. Durable Viewer identity retained at version 6; do not re-deliver d60449c or 961d43d. The package is usable locally; actual PC holdings connection and new-screen visual verification remain pending.

### Earlier actual application and event-view continuation — 2026-09-24

- Attachment `CRYPTO_RECOVERY_RESULT(2).json`: 42,165 bytes, SHA256 `76e61f0408e2c815ef518dede2c44c7306ddd0cf75ee678e6d93f1eb54a18b80`, read locally only. Actual PC moved from `c5ffd52` to `4af291dd9b0a3266959cfc1b15ee0309f07daa8f` on `recovery/paper-20260924-110445-3a82105c`.
- Verified pre-activation backup `20260924-110445-3a82105c/auto_demo.sqlite3`: 3,081,179,136 bytes, integrity OK; research accounts 775 / fills 24,508 / feedback 11,832; lab accounts 4,650 / trades 7,471 / metrics 12; intelligence events 73 / stored horizon responses 176. These are backup-time counts; no event-price table existed then.
- Actual observation 11:05:19–11:08:22 KST: PAPER, memory, lab account/metrics, all four exchange/BTC/ETH flow streams, OHLCV and event receipts advanced. New event-price table became readable, latest archive 11:05:21 KST; intelligence reported 1,376 preserved-price writes. This verifies initial archive accumulation, not complete reaction coverage or subsequent uninterrupted uptime.
- OHLCV recovered after two lock deferrals: collected 16 markets / 422 writes, consecutive deferrals 0. Notices recovered after one deferral. Runtime owner checks now match for host/research/PAPER/flow/forward; each host role started once with no current exit. Historical crash-string matches in old logs are not a new failure.
- Latest intelligence run: 775 exchange/markets, 3 events, due 8,359 / future 775 / already captured 166 / missing baseline 8,047 / missing target 312; inserted 0, source and response failures 0, archive baseline/target usage 0. These are event×market×horizon attempts. Response timestamp remains 11:01:03 KST. A three-minute observation does not establish later archive consumption; missing outage-era prices remain missing.
- B3/aggressive still has six reconciled fills / three closes / two wins, zero holdings and PAPER realized +348,855.81 KRW. Its source/account clocks advanced. No additional B3 fill or strategy-superiority claim.
- Implemented the next read-only slice: `event_reaction_view.py` now joins completed reactions and archived partial prices for the selected coin plus same-exchange BTC/ETH. Bounded archive candidates use at most 80 metadata IDs and exact event/clock/source/type/provider/market keys. Revised clocks remain separate; conflicts cannot borrow old anchors. Saved reactions keep their own prices. Pending points reuse strict archive validation; no reaction is calculated or written by the view.
- Event UI displays stored prices before the first completed reaction and distinguishes waiting, missing baseline/target, calculation pending and invalid records. Saved 0% remains distinct from missing. Same-event BTC/ETH samples are visible while missing coin returns stay null. Full event identity and selections/open details/focus survive polling, including unchanged account revisions. No CSS layer or collector/PAPER rule change.
- Verification: 33 affected Python tests + 14 JS/API/DOM tests passed; TypeScript and changed-module syntax/compilation passed. Read-only HTTP returns actual fixture archive prices, rejects mutation, preserves DB hash. Latest-20 event projection fits the existing transport budget; completed prices are not duplicated. Tests use temporary fixtures; actual PC event rows and browser visual acceptance still require the new read-only Viewer. Existing localhost-browser policy limitation remains; no bypass attempted.
- Packaged/read-back verified: `CRYPTO_STRATEGY_REVIEW_d60449c.zip`, source `d60449c7b60327d49b0198af851d0fed17d691dc`, 34 files / 71,290 bytes, SHA256 `849ccbde290c1ef2b63d51f15baf20e7f8db61fc439e815fb530cf66eb0fc769`. Extracted Python `-B -S` verified its full manifest and read real temporary-SQLite event rows with the DB hash unchanged; the extracted JS rendered the same preserved baseline and null pending return. This is fixture evidence, not an actual-PC visual pass. Durable Viewer file replaced at version 5; verified collection package/source remains 4af291d.
- Run the new folder's `RUN_REVIEW.cmd` while retaining the verified collection session. No new recovery package or collector restart is needed for this Viewer change.

### Earlier actual recovery evidence — 2026-09-24 01:45–01:46 UTC / 10:45–10:46 KST

- Attachment `CRYPTO_RECOVERY_RESULT(1).json`: 32,287 bytes, SHA256 `935624e1404f2934acdc4201090d2a9a7f7fc2d24ea5e3b20078b0e0999f2699`; read locally only. Actual source receipt: original `56b9361` on the primary branch → pinned `c5ffd52423a4a8bcfbb109fce5829f401322087f` on `recovery/paper-20260924-104520-7f48fa08`. This old recovery package does not prove `4af291d` application. The intervening return to the primary branch is not explained.
- Consistent backup `20260924-104520-7f48fa08/auto_demo.sqlite3`: 3,081,179,136 bytes, `quick_check=ok`; counts: research accounts 775, fills 24,502, feedback 11,830, Strategy Lab accounts 4,650, trades 7,466, metrics 12. Compared with the September 23 verified backup: +1,368 research fills, +652 feedback rows, +459 lab trades. This older helper has no event backup counts.
- Observation 01:45:53.664 → 01:46:54.309 UTC: PAPER, market memory, lab account clock, all four exchange/BTC/ETH flow clocks, event receipts and reaction captures advanced. Latest event/reaction receipt: 01:45:55.433 UTC. Missing count/coin/horizon breakdown prevents claiming B3 or full reaction coverage. OHLCV receipt stayed at 01:39:24.987 UTC during this minute; old helper lacks per-cycle results, so a healthy badge does not prove a new write.
- After-start inventory shows recovery plus forward/market_flow/research/paper launcher-child pairs; each host child started once and was running at capture. Old reviewer labels native Windows venv children unresolved and owner checks false; known lineage/creation-clock fixes are in the unapplied package. Historical log matches/pre-start stale status do not establish a new collector failure.
- Bithumb/B3/aggressive still reconciles six fills, three closes, two wins, zero position, cash/equity 10,348,855.81 KRW and cumulative PAPER realized +348,855.81 KRW. No new B3 fill; three closes do not establish strategy superiority. Account/source clocks advanced; fill-only replay cannot reproduce drawdown.
- Delivery renamed `CRYPTO_PAPER_RECOVERY_4af291d.zip`: unchanged verified 18-file/37,520-byte package, SHA256 `b044679eb996d88d9d71c51ba0dff5d55f6a84e7e0a7ae3f8d3660aaf204ee64`, internal folder `CRYPTO_PAPER_RECOVERY_4af291dd9b0a`. Filename, folder, launcher title and manifest identify the same source. Full manifest rechecked; no rebuild or repeated tests. Durable file identity/version preserved.
- If the old recovery session remains active, Ctrl+C in that session and wait for termination before launching the new folder. Never kill arbitrary Python processes or switch Git under active collectors. New helper checks stopped state and backup; unresolved children block activation. Keep the new session open, then inspect its new result.

### Earlier actual continuation evidence — 2026-09-23 15:54 UTC / September 24 00:54 KST

- Verified schema-2 input `CRYPTO_CHECK_RESULT.json`, 47,265 bytes, SHA256 `e0adb5c74ac30f2a47c46dd8d7aa6fbc16de181b2f5cfdf856f0c8f3079b3575`; reviewer source 39c2740 with matching package hashes. Read locally only. Two observations completed 15:54:00–15:54:33 UTC. Canonical DB file remains 3,081,179,136 bytes; file size alone is not an accumulation measure.
- Same collector PIDs/creation times as the 11:12 report were observed about 4h42m later, with one start per owned role. Host ownership now verifies. PAPER/memory and all four sampled BTC/ETH trade streams advanced across T0/T1. B3 source memory advanced to 3630772, account/source times to 15:51:42/15:51:06 UTC; all six fills still reconcile with cumulative PAPER realized +348,855.8087190897 KRW. No extra B3 trade is required for a successful scan.
- Latest OHLCV cycle reported 16 markets / 8,342 rows written, with five-minute cadence; an unchanged 33-second clock is not a failure. Notices received 18 rows, inserted 0. Intelligence source failures and reaction execution failures are both 0. Latest event-reaction capture advanced to 15:14:49 UTC (September 24 00:14 KST), establishing new reaction writes since the previous report. This timestamp does not prove B3/BTC/ETH or all horizons are covered.
- Last eligible reaction cycle: 775 exchange/market pairs, two events, 4,643 due observations, 1,550 future observations, seven already captured, 4,617 missing baselines and 26 missing targets. These are event × market × horizon attempts, not distinct missing events or coins. The explicit BTC review sample is still the older September 11 event; it does not identify the newly captured rows.
- User then stated the server is now off. Outage-time prices may never have been collected and can explain missing baselines. No claim that pruning caused these specific 4,617 gaps; no live-PC restart or stop was performed here. A stopped web app and stopped collectors are separate; the report proves collectors alive only during its observation.
- Separately reproduced source defect: raw flow keeps 20,000 trades per market and could prune the event baseline or exact target before the first completed reaction. The collector previously preserved a baseline only after a completed response. A fixture using the real prune function reproduces that retention loss independently of an outage.
- Implemented additive `research_intelligence_event_prices`: preserve at most baseline + four exact target observations per known event/clock/exchange/market before raw pruning, in the same transaction. An early reaction pass also saves its baseline before 15m is due. Later reaction calculation consumes these exact ticks with unchanged direction/tolerance/provider/source clocks; existing valid saved-response baselines retain priority. No substitute prices, new requests, scoring/PAPER rule changes or historical response rewrites. Failed preservation rolls back before deletion; raw retention remains 20,000.
- Preservation only helps event prices actually observed while relevant event metadata exists. Offline periods, late discovery after pruning and illiquid periods stay missing. Revised event times and other exchanges cannot borrow an archived price. Only a later observed closer tick can improve a pending archive point; completed responses remain immutable.
- Backup-first recovery now compares existing event/response/archive table counts as well as the six trading tables before source activation. Missing archive tables are not created by the read-only backup. New schema is created by the source owners only after a verified user-started recovery. Version-labelled recovery folders avoid running the old archive. Read-only review ZIP remains 39c2740; PC source last verified at c5ffd52 is not silently upgraded.
- Verification: 70 distinct affected Python tests passed, including real pruning → restart → 12 exact coin/BTC/ETH horizon responses → Viewer values, outage/tolerance nonfabrication, clock/exchange isolation, future-tick exclusion, transaction rollback, WAL backup/event row readback and existing flow/ingest/downstream checks. Changed modules compile. Extracted recovery package verification follows the pinned commit. Actual-PC application and new archived-price accumulation remain pending.

### Earlier continuation evidence — 2026-09-23 11:12 UTC

- User supplied `CRYPTO_B3_REVIEW_RESULT(2).json`, 36,463 bytes, SHA256 `66db5b61a81ff415b491558fba281251c4b4192110b6089408b6587ebb3ce0c1`, and reported closing the collection session once. Attachment read locally only. At 11:12:04–11:12:36 UTC (20:12 KST), native process discovery found forward, market-flow, research and PAPER roles. Their current generation began around 11:12:02 UTC; this file does not prove shutdown cleanup or automatic restart, nor current liveness after the observation.
- Bithumb/B3/aggressive retains the exact previous five fill rows and adds one PAPER sell with ledger time 10:50:11 UTC (19:50 KST), source memory 3559614, price 1.083458, realized +358,806.34216817166 KRW. Six-fill replay matches the account: cash 10,348,855.80871909, quantity/average zero, cumulative realized +348,855.8087190897, three closes/two wins. Account/source clocks advanced to 11:08:24/11:08:11 UTC. This verifies scoped ledger continuity, not broad strategy superiority or real-money performance; drawdown is still not fill-only replay.
- OHLCV latest receipt advanced between reports to 11:00:41 UTC (20:00 KST). PAPER and memory advanced across this 32-second observation. Trade-flow T1 was current but T0 timed out, so its paired change is unknown. Reaction latest capture remains the old September 11 value; no B3 reaction is established by the explicitly separate BTC fallback sample.
- This attachment has the earlier reviewer schema: no source version, collector result, account/metrics separation or event receipt-clock metadata. Its events=0 and historical crash categories cannot establish a current ingest failure or crash. Exact reviewer revision cannot be recovered from this file. The PC's last verified source remains c5ffd52 on the previously recorded local recovery branch; this report contains no new Git observation.
- The updated read-only package adds `RUN_CHECK.cmd`: collect two observations, save `CRYPTO_CHECK_RESULT.json`, then exit without a server/browser. The extraction folder and launcher show the source revision. Results record schema 2, verified package file hashes/source identity and observation times; mixed files fail before DB review. This package identity is never labelled as the separate PC runner revision. Ctrl+C records an interrupted observation; abrupt process termination can still leave incomplete evidence.
- Existing `RUN_REVIEW.cmd` remains available for the coin workspace; an occupied port no longer overwrites a prior result before failing. Saved event response output now preserves the observed-market count/selection as well as missing baseline/target counters. Neither reviewer starts, stops or changes collectors, Git, the canonical DB or credentials.
- Verification: 26 affected session/runtime/journal tests and changed-module compilation passed. Real six-fill comparison and the unchanged five-fill prefix were checked against the two uploaded reports. Extracted archive verification follows the committed build. Native Windows launcher execution of this revision, event reaction growth, long-run coverage and UI visual acceptance remain pending.

### Earlier recovery evidence — 2026-09-23 10:50 UTC

- User supplied `CRYPTO_RECOVERY_RESULT.json`, 30,852 bytes, SHA256 `56a450646bd34c27498475c9b3e827aabedc1eefe495fbdaa9ddea970a98b216`; read locally only. Windows activated `c5ffd52423a4a8bcfbb109fce5829f401322087f` on `recovery/paper-20260923-194932-741dec34` from actual `ba3c59a` / primary branch. The 3,081,179,136-byte pre-start SQLite backup passed quick_check and six account/ledger count comparisons.
- Native observation 10:49:58–10:50:59 UTC: PAPER accounts, market memory, all four BTC/ETH trade streams, Strategy Lab aggregate metrics and event receipt clocks advanced. Four collector owners started once, no reported fresh error categories. App/holdings/publish/deploy stayed excluded. This proves partial persisted activity, not complete coverage or long-term liveness.
- OHLCV and event-reaction clocks did not advance during this first minute. The B3 aggressive account/source timestamps also remained old, although all five fills still reconcile (two closes, one win). Aggregate metric refresh can occur without consuming any new source rows; it must not imply this coin account is current.
- The report exposes Windows venv launchers plus their same-role interpreter children. Earlier scope logic did not recognize the latter, and the backup delay exceeded the old 30-second host start tolerance. The corrected direct-parent/time/PID checks resolve all five saved owner identities against this uploaded observation. This is report re-evaluation, not a new live PC probe. Native shutdown remains untested.
- Source-confirmed collection defect: research lock deferral was labelled healthy and delayed the next probe for a full normal interval. It now preserves the last-success clock, reports deferred and retries lock probes after 5/10/20 seconds (20-second cap). Normal successful collection intervals and lock ownership remain unchanged. Explicit ok=false is degraded, not healthy. Actual OHLCV's saved result is needed before claiming the lock caused this particular missing update.
- Read-only evidence now includes allowlisted collector outcome/counters, event missing-baseline/target and future/due counts; no raw logs, command lines, errors or credentials. Strategy Lab account activity and aggregate metric refresh are separate series. Unknown remains unknown. The revised review archive can inspect the currently running PC without restarting collectors.
- Verification: 34 affected Python tests passed, Build 69 contract and changed-module compilation passed. Actual uploaded lineage re-evaluation matches all owner PIDs. No running PC process or database was modified by this agent; the retry fix is source-only until a later controlled code update. The existing collection recovery ZIP remains pinned to c5ffd52.

### Earlier inventory and implementation history

- Latest actual Windows evidence: `CRYPTO_B3_REVIEW_RESULT(1).json`, observed 2026-09-23 04:28:50–04:29:23 UTC: actual account/ledger projection matches, native process discovery succeeds with no matching runners. The new report does not contain Git HEAD. Last actual Git observation remains the September 21 clean `b3-auto-trader-phase1@ba3c59a50962ae1a5bdc41053a75f9e6bf9e1ec7`; recovery must recheck it. Remote primary remains `56b9361f352eedce2e543b3baca36952b2397d76`.
- Canonical `b3_trader/data/auto_demo.sqlite3`: 3,081,179,136 bytes. Latest PAPER/memory activity remains September 21 around 06:23 UTC, about 46.1 hours old at the latest observation. T0/T1 did not advance. Historical healthy badges do not prove liveness; shutdown cause is unestablished. Latest input has no new WAL inventory.
- Actual counts: PAPER accounts 775 / fills 23,134; Strategy Lab accounts 4,650 / trades 7,007; market memory 347,777; OHLCV 1,639,206; trade flow 2,863,417; intelligence events 70 / responses 10. Responses cover one event and BTC/ETH only, with no 1d or altcoin samples.
- Bithumb/B3/aggressive: 5 fills, 2 closed trades, 1 win. Full diagnostic replay matches cash 9,003,349.466550918, quantity 1,242,359.8884979396, average 0.7942143087, realized -9,950.53344908182; no replay differences. Global aggressive 1,039 closed trades is a separate scope. Stored maximum drawdown is not reproducible from fills alone.
- `manual_holdings` is absent in this DB; source owns holdings through `Settings.journal_db` (default `b3_trader/data/crypto_trader.sqlite3`). That other actual DB has not been inventoried. Do not invent holdings loss or initialize new tables.
- Implementation checkout: isolated `agent/crypto-product-data-recovery-20260921`, based on recovery checkpoint `368d4d9`. It is not the user's Windows runtime. No canonical DB write, runtime restart, Production deployment, real order, automatic merge or holdings mutation occurred.

### Implemented vertical slice

- Read-only consistent coin/exchange account projection now includes quantity, full precision, complete per-experiment ledger, fee-aware replay, scoped wins/return and revision identity. Removed the old shared 80-fill truncation/latest-only gap.
- Existing execution predicates and sizing are shared with the plan projection, preserving strategy/PAPER behavior. Plan exposes next entry, weight, conditional later rounds, actual full-position take-profit and stop rules; no invented partial-sale strategy.
- Existing D1 detail transport can store complete immutable ledger chunks. Authenticated API paginates by experiment and revision; changed revisions return 409 instead of mixing account and old fills. Pending rotations retain their place under existing write budgets.
- Paper route now keeps coin fixed across strategy tabs, account, price/fill chart, complete ledger and fee-inclusive split calculator. BTC/ETH comparisons use aligned stored 1h closes; events show only actual selected-coin responses. Missing observations stay missing. Old aggregate/basic-strategy pages remain reachable in the full Viewer.
- New view has one owned Shadow DOM stylesheet; preserves draft, focus and disclosure state during polling and follows the existing theme. Cross-exchange holding fallback and ticker localization corruption are corrected. No global strategy sample is presented as coin validation.
- Standalone stdlib review server opens the same projection/UI against the existing PC DB in read-only mode. Bind is loopback only; mutation routes, foreign origins and nonlocal hosts are rejected. `scripts/build-strategy-review.py` packages it with `RUN_REVIEW.cmd`; no DB, secrets, seeded data, Python dependencies or installer are included.

### Verification and limits

- New Python projection/journal/context/HTTP tests: 8 passed; existing affected Strategy Lab/custom/candidate/write-budget tests: 10 passed.
- Pre/post execution differential: 5,000 randomized cases matched fills, balances and learning (excluding wallclock metadata). Shared-rule extraction does not authorize strategy changes.
- JavaScript API/model/DOM tests: 12 passed, covering complete pagination, revision/chunk integrity, fee/quantity conservation, exchange/quote isolation, polling continuity, theme, identifier fidelity and preservation of original account pages.
- TypeScript and all existing Viewer static gates passed; changed Python modules compile. Extracted archive runs with Python `-S`, serves every packaged asset and reconciles a fixture account with unchanged DB hash. Static gates and DOM tests are not visual acceptance.
- Browser local navigation was blocked by this session's browser policy. Desktop/mobile visual acceptance remains pending; the September 23 actual-PC report below verifies the new account/ledger projection. No screenshots or visual PASS are claimed.
- Remaining data gaps: sustained collection coverage and event-reaction diagnosis; altcoin event reactions / 1d horizons / historical same-type samples; real-holdings workflow redesign and small-live comparison. The rejected live-trading page is not declared redesigned or accepted.
- Transport limit: a single coin whose complete chunks exceed its per-run write budget fails explicitly; no silent truncation. Future chunk retention and very large journals need a separate bounded storage plan.

### Event reaction continuation — source complete, PC verification pending

- Parent for this unit: `a8c3545`. No new Windows review result was supplied or found; the actual-runtime evidence above has not advanced. This unit changes source, not the currently running PC or Production.
- Default event-response targets now include KRW markets from both REST and WebSocket registries; older DBs can discover observed raw markets. Explicit benchmark lists remain exact. No new source feed, network request, score or order path is added.
- A validated previously captured reaction supplies the same baseline for later horizons after raw-trade pruning. Conflicting/revised event clocks or corrupt saved samples fail closed; existing rows are not rewritten. Future ticks cannot satisfy a present target. No schema change or canonical DB mutation is required for this source change.
- Event projection groups by captured event clock and joins the same exchange, provider, source and horizon. It exposes baseline/target prices and exact timestamps for the coin, BTC and ETH, plus relative percentage-point movement. Invalid observations stay nonnumeric and are flagged.
- Historical samples use the same coin/exchange/source/event type/provider over the preceding year and only results captured before the selected event. Future events and late backfills cannot inflate that historical comparison. Counts, mean, median and positive counts remain separate from any recommendation probability.
- The event tab now selects one event and connects reaction numbers, original publication link, historical samples and actual price/time evidence. Selection and disclosures survive polling, including arrival of a newer event.
- Verification: 21 Python collection/journal/context tests + 13 ingest/check/downstream-sensitivity tests passed; latest changed collector tests 6/6 passed. JS/API/DOM 13/13 passed; all existing Viewer type/static gates and changed Python compilation passed. Extracted stdlib archive returned the same stored event prices/returns through HTTP and the local report, served every asset, and left the fixture DB hash unchanged.
- The existing review archive now also emits one explicitly scoped event sample. It uses B3 if present, otherwise labels a BTC sample separately; no BTC observation becomes B3 evidence.
- Limits remain: first capture still needs a real baseline and target inside existing raw retention; this does not reconstruct never-recorded prices or repair a stopped process. Unsupported event feeds, actual PC application, live accumulation and visual acceptance remain pending. New schema/pinned-price storage would require a separate additive change with actual DB backup/readback first.

### Runtime supervision continuation — source complete, PC verification pending

- Parent for this unit: `c3f828c`. No new actual-PC review result was received or found. The Windows runtime/DB evidence above has not advanced; no process was restarted or canonical data changed.
- Found in source: the launcher printed ON immediately after starting hidden sidecars, then blocked on the app and did not observe sidecar exits. Sidecars only restarted during app code-update exit 75. This source defect is not an established cause of the historical whole-PC outage.
- `local_process_host.py` now owns the existing launcher session and exact sidecar modules/arguments. It holds a per-checkout OS lock, records child exit codes and bounded rotating logs, retries failed collection/PAPER processes after five seconds, and observes app shutdown before retrying children. App exit 75 cleans up and returns to PowerShell so the updated host module is reloaded. Normal app exit or a stop request ends the session. Cleanup failure returns a non-retry exit instead of duplicating unresolved children.
- Holding-consumer startup arguments and its app-update/shutdown lifecycle are preserved; no new automatic retry policy is added. This source change grants no permission to run it on the actual PC. Strategy/PAPER execution predicates, control flags and databases are unchanged.
- `runtime_review.py` reads scoped Windows process identities, saved component/exit metadata and bounded error classifications. It does not export raw command lines, log bodies, environment values or credentials. A failed process lookup or ambiguous checkout remains unknown. Stored healthy labels never become live-process proof.
- The same read-only review archive now records T0/T1 DB activity 30 seconds apart, alongside the existing account/ledger/event evidence. Unchanged timestamps are an observation, not proof of collection failure; slow/missing queries stay unknown. The archive includes no process host or collector executable and cannot apply the recovery code.
- Verification: 25 distinct affected Python tests passed (including real fixture subprocess crash/retry, app-only restart, code-update cleanup of all owned roles, duplicate-host exclusion, stop cancellation, cleanup-failure non-retry, and read-only evidence). Build 69 ownership/static contract and changed-module compilation passed. Extracted 32-file archive ran with Python `-B -S`, reconciled the same fixture account over HTTP, completed both observations, kept unsupported process checks unknown and left the fixture DB hash unchanged.
- Native Windows/PowerShell execution and actual-PC DB-to-Viewer acceptance remain NOT_RUN. Existing GUI tests were not repeated because the Viewer source did not change. No visual acceptance, collector-growth proof, new actual outage cause, primary merge or deployment is claimed.

### Actual-PC review received; collection recovery prepared — 2026-09-23

- Actual input: `CRYPTO_B3_REVIEW_RESULT(1).json` (30,788 bytes; SHA256 `cec28abc9448448ae248e357508b33b490ce91b7b89af4ed03b85a807e1be2ca`), read locally without uploading private records. Observed 2026-09-23 04:28:50–04:29:23 UTC. New read model reconciles the actual Bithumb/B3/aggressive account: all 5 fills, 2 closes, 1 win, no differences. This is numeric acceptance, not visual approval; saved drawdown remains outside fill-only replay.
- Both native Windows process queries succeeded with no matching processes. Relevant stored activity was about 46.1 hours old; PAPER/memory/lab/OHLCV/reaction timestamps did not advance over 33.5 seconds. Historical permission-denied/database-lock errors are not a proven cause of the whole-PC shutdown. No actual-PC process was started in this coding environment.
- Fixed two observed review gaps: event freshness now uses positive `received_at` (zero stays missing), and raw trade activity uses four explicitly scoped BTC/ETH exchange streams through the existing time index instead of an unbounded all-market receipt-time scan. Added receipt clock/scope metadata. Unknown or partially readable process state cannot authorize startup.
- Added a collection-only host/research profile: forward, market flow, research and PAPER owners; the research allowlist retains warehouse, exchange notices, OHLCV, intelligence, Upbit PAPER and Strategy Lab. Saved disabled controls remain disabled. Cloudflare publication/deploy, the real-holdings consumer, local app, Telegram and automatic Git synchronization are excluded. Control changes cannot re-enable excluded components; disallowed service constructors are not called.
- Added a separate `CRYPTO_PAPER_RECOVERY.zip` builder and user-started launcher. It verifies bundle hashes, current processes, clean local Git, expected origin, pinned ancestry and existing Python dependencies. It makes a consistent SQLite backup including WAL, checks disk space, runs backup integrity/ledger-count readback, rechecks processes/source, then creates a local recovery branch at the pinned commit. The primary branch ref and remote branches are unchanged. No reset, seed, package install, credential edit or strategy/PAPER calculation change.
- The session supervises only its own children and saves private `CRYPTO_RECOVERY_RESULT.json` every minute, including source/backup receipts, T0/latest DB clocks, native process evidence and the current B3 account/ledger reconciliation. Ctrl+C stops the session; uncertain cleanup produces a non-success result. The recovery branch is deliberately retained after stopping. The earlier read-only review ZIP remains separate and unchanged.
- Moved the initial PAPER status write inside its existing store-close guard, so a startup PermissionError no longer skips store cleanup. This is a verified error-path correction, not a claimed explanation of the historical outage.
- Verification: 44 distinct affected Python tests passed, covering WAL backup/source preservation, missing DB/low space/existing destination, dirty/changing Git, backup-before-activation, active/ambiguous processes, profile control isolation, permission-error cleanup, host retries and prior research ownership. Build 69 contract and changed-module compilation passed. Synthetic fixtures only; native Windows execution and renewed canonical accumulation remain pending.

### Exact next action

1. Keep the verified 4af291d collection session open. Do not rerun recovery or switch its checkout for this read-only Viewer.
2. Run the newly version-labelled strategy review package outside the checkout. Close only the old review session if it owns port 8766; open the new folder's RUN_REVIEW.cmd and choose 실전 계획.
3. Inspect the actual separate manual-holdings connection, exact exchange/coin amounts, strategy-ledger navigation and fee-aware split calculations from the new screen/report. Missing journal/configuration is not evidence that holdings were deleted. Keep prior event gaps missing; actual archive use is now observed globally but B3 baseline remains unavailable for the supplied event.
4. Next: resolve concrete real-holdings evidence/UI issues, then manual small-trade comparison and broader main-Viewer integration. No Production deployment, primary merge, live order, strategy/PAPER change, holdings mutation or destructive DB operation. V22 remains rejected.


## Current phase

Local multi-asset PAPER monitor + beginner-facing dashboard + secure Cloudflare phone access + adaptive Bithumb-wide per-coin PAPER research + verified Build 38 market lifecycle foundation + Build 39 pre-KRW CEX listing-history foundation + Build 65~71 DEX v2 forward-only validation track + Build 48 senior-default Viewer UX pass.

## Program roadmap

The program-level source of truth is now:

- `docs/workstreams/dashboard-v1/MASTER_ROADMAP.md`
- Viewer omission/regression checklist: `docs/VIEWER_REBUILD_CHECKLIST.md`
- Existing dashboard-v1 continuity checklist: `docs/workstreams/dashboard-v1/TASKS.md`
- Permanent modular dependency rules: `docs/MODULAR_ARCHITECTURE.md`

The master roadmap merges the already-completed strategy analytics work with the remaining real-holdings history / records / CI / Phase 5~8 / mobile QA work and adds the market-intelligence program: automatic listing/delisting lifecycle, pre-KRW CEX/DEX history, D-5 returns, multi-facet sector/geography, flow/CVD, technical structure, news/macro/human/onchain intelligence, unified score v2, AI interpretation, PAPER v2, walk-forward and candidate promotion.

Do not jump directly from raw new features into the current PAPER strategy. Required promotion path is:

`collect → persist → quality/reaction validation → shadow score → parallel PAPER A/B → walk-forward → candidate`.

## Modular architecture — permanent rule

Dependency direction:

`collector/source → store/repository → feature/domain → score/decision → service/API → page/view`

Do not put reusable calculation, exchange fetch, SQL, scoring formula or long-lived cache into `pages/*`.
Do not put indicator/event/lifecycle formulas into supervisors. Supervisors only orchestrate modules.
If equivalent logic is needed twice, extract the shared owner before continuing.

UI continuity is owned by:
- `cloudflare-pages/public/modules/shared/ui-continuity.js`

No page-specific `scrollTop` copy/paste and no broad DOM `MutationObserver` continuity workaround.

## Build 48 senior-default Viewer UX pass

Primary target user is a Korean crypto buyer/seller in their 60s who is not expected to interpret developer, quant or internal research terminology.

Completed in the current Build 48 pass:
- `cloudflare-pages/public/index.html` enables `data-reader-baseline="senior"` and loads `senior-default.css` last so older density rules cannot shrink the default interface again
- common body/menu/meta copy is raised toward a 13~16px hierarchy; routine controls target at least 44px and key inputs 48px
- existing `content-priority.css` remains authoritative for visual order; it already pushes coin-finder listing research, holdings history and sector research material behind the primary user task flow even when source render order is older
- combined and per-exchange current PAPER results present a normalized 10,000,000 KRW comparison instead of leading with the sum of many independent virtual accounts
- strategy detail uses the same 10,000,000 KRW normalized comparison basis while underlying strategy/PAPER source calculations remain unchanged
- numeric strategy ranking was removed from the default list; `수익률 높은 순` is explicitly described as a sort order rather than a recommendation rank
- experiment IDs were removed from the default strategy list/detail summary; research IDs remain only in deeper evidence/comparison surfaces
- `shared/holding-plan.js` converts the existing PAPER `trade_plan` into ordinary-language holding guidance without creating new trade logic
- the default holdings flow now answers `지금 물타기해도 될까?` first, then shows next review price, remaining/total rounds, stop-adding level, target reference and current PAPER suggested weight
- because actual holding exchange is not yet stored, the Viewer requires an explicit Bithumb/Upbit reference selection before presenting holding-plan prices rather than guessing an exchange
- the user can enter a total additional-buy budget; the first round uses the current real PAPER `next_add_price`, later rows are explicitly labeled estimates based on the current `add_step_pct`, and no row is generated at/below the PAPER hard stop
- the holding plan states stop conditions: no remaining rounds, sell/error state, hard-stop boundary, or weakened conditions on the next strategy recalculation
- profit protection is shown as three price/condition stages using existing PAPER fields only: first protection activation, dynamic target, and trailing high-water protection; no arbitrary 30/30/40 partial-sell ratio is invented
- a persistent global `간편 보기 / 상세 보기` mode is implemented. `간편 보기` is the default and hides specialist research scores, deep charts, secondary calculators and internal evidence while `상세 보기` restores the existing surfaces without deleting data
- Records now defaults to `내 매매·판단` with buy/sell/decision changes only; `시스템·학습` is a separate persisted scope for learning adjustments, errors and safety blocks
- high-frequency holding/Records copy has been moved toward ordinary Korean while technical evidence remains available in detail/internal views

Still open in this UX pass:
- material US macro schedule / major US market index / material news must consume the existing Phase 5 calendar/news data contract; do not create a Viewer-only collector or fake current-event placeholders
- persist actual holding exchange in local holdings data so the reference exchange can be preselected automatically
- staged profit protection deliberately has no partial-sell percentages until a real allocation/execution policy is defined
- complete remaining terminology cleanup where it does not damage technical accuracy
- add consistent non-color state cues (`▲/▼`, 수익/손실, explicit status text)
- desktop and current-phone screenshot/interaction QA remains required

Validation note:
- Build 48 source changes remain Viewer-only and do not alter PAPER order logic, strategy selection logic, DEX forward-validation rules or live-trading boundaries
- commit `8686fb8` completed 28 GitHub Actions with no failure/queued/in-progress result
- the newer simple/detail + Records split head must complete its own Actions before Build 48 code validation is marked closed

## Current market-intelligence implementation status

Build 38 completed and live-verified:
- shared same-page UI continuity guard is installed at the Viewer app root
- same-route router rerenders preserve scroll/focus state through the shared owner
- `b3_trader/market_lifecycle.py` owns pure lifecycle classification and lifecycle PAPER entry policy
- `b3_trader/market_lifecycle_store.py` owns additive lifecycle SQLite tables/events
- first lifecycle observation is treated as baseline so all existing markets are not mislabeled as new listings
- a market appearing after baseline becomes `NEW_LISTING`
- exchange warning/caution maps to `CAUTION`
- market disappearance requires 3 accepted observations before `TERMINATED`
- a severely incomplete/empty market-list response is rejected before it can increment missing counters
- `b3_trader/market_notice_sources.py` owns Bithumb/Upbit official notice adapters
- `b3_trader/market_notice_timing.py` owns pure structured timing extraction
- `b3_trader/market_notice_store.py` owns notice/event state persistence and additive timing columns
- structured timing fields are `announcement_at`, `deposit_at`, `trade_open_at`, `termination_at`; date-only wording does not invent midnight
- `b3_trader/market_notice_audit.py` provides compact read-only live-source/timing coverage inspection
- `b3_trader/market_lifecycle_service.py` composes market-list state with official notice state and owns the lifecycle entry-policy service boundary
- `market-notice-watch` runs as a separate supervisor sidecar and cannot place orders
- lifecycle state and `notice_only` announced listings are projected through the bounded Cloudflare snapshot
- the sector Viewer renders a modular lifecycle panel for listing-announced/new/caution/termination states and structured schedule times
- lifecycle panel refreshes only its own DOM on snapshot polling; it does not rerender the whole page
- D-5..D-1 completed prior-day return windows reuse `research_market_memory_mx`; no duplicate per-widget exchange calls
- all active KRW markets are already seeded through the existing all-market PAPER account/profile path; newly discovered markets therefore bootstrap their account/profile before scoring and begin market-memory collection on scan
- `TERMINATION_SCHEDULED` and `TERMINATED` block new/additional PAPER buys while existing positions can still be sold/managed and historical performance remains stored
- CAUTION and NEW_LISTING remain shadow information in the current adaptive strategy; broader lifecycle scoring stays deferred to Unified Score v2/PAPER v2
- normal launcher owns Bithumb PAPER through `paper_runtime_supervisor`; stale/dead/reused PID cannot suppress recovery
- Cloudflare D1 writes are bounded at snapshot 60s / detail 300s with capped detail batches and unchanged-row skipping
- Windows live verification confirmed notice/snapshot/detail components healthy, PAPER `running/fresh`, valid asset registry and current Viewer snapshot

Build 39 pre-KRW CEX foundation completed in source/CI, live data QA pending:
- `listing_identity.py` owns the fail-closed identity gate; ticker-only matching is forbidden
- `/api/coin-profile-identity` reuses verified/corroborated `coin_profile_cache` identity via INGEST bearer authentication rather than duplicating project research
- existing CoinGecko evidence is surfaced as a stable `coingecko_id`; multi-source/CMC provider ids are not assumed to be CoinGecko ids
- `listing_venue_verifier.py` requires exact CoinGecko coin-id + venue identifier + base/target pair before foreign candles are accepted
- initial public CEX adapters are Binance, OKX and Bybit; each normalizes to the shared `ListingCandle` domain
- `listing_history_planner.py` seeds only official KRW listing notices and rejects Upbit USDT-only notices as KRW cases
- listing case keys use stable domestic notice id when available; changed trade-open schedules update the same case
- `domestic_listing_price.py` resolves the domestic listing start price from public 1-minute candles around `trade_open_at`, not from current ticker price
- additive local SQLite owns `listing_history_cases`, `listing_history_sources`, `listing_history_candles`, `listing_history_features`
- prelisting windows are T-7d/T-5d/T-3d/T-1d/T-6h/T-1h; postlisting tracking is +5m/+1h/+6h/+24h/+3d/+7d
- unknown foreign launch time/first price stays null; the first candle of the bounded T-8d research window is never treated as a historical CEX launch price
- when a venue exposes a launch timestamp, first price is resolved only from a narrow launch-time candle window; Binance may use its explicit first historical kline path
- `tracking_postlisting` remains active until 7-day reaction data can mature
- `listing-history-research` is an independent 15-minute supervisor component, processes at most 3 cases per run, and has no PAPER score/order authority
- `listing_history_audit.py` provides read-only case/status/identity/source/candle/feature audit output
- `scripts/check-listing-build39.py` and dedicated `B3 listing Build 39` workflow enforce the modular/ticker-safety/PAPER-unwired contract
- `scripts/verify-build39-runtime.ps1` performs contract → Pages deploy → one bounded live cycle → audit; `-StatusOnly` checks the supervisor component and accumulated DB state

Build 65~71 DEX v2 forward validation track:
- Build 65 retired the failed retrospective v1 hypothesis and froze v2 components, 0.60/0.40 weights, directions, `2026-08-31T00:00:00Z` cutoff and forward validation criteria before scoring
- Build 66 scores only usable post-cutoff cases and never back-scores pre-cutoff cases as v2
- Build 67 ingests current official Bithumb/Upbit KRW listing notices; Build 68 enriches at most one post-cutoff case per run
- Build 69 composes one Build 67 intake, one bounded Build 68 enrichment and one Build 66 audit; it does not reactivate generic historical supervisors or Build 47 cursors
- Build 69 now also owns a dedicated 15-minute scheduled process. `run-local.ps1` starts, restart-cycles and stops it with the normal server; server-off means zero scheduled network/DB work
- normal launcher sets `DEX_FORWARD_PIPELINE_DEDICATED_MODE=true`, which forces the generic `listing-history-research` and `dex-launch-research` components off without mutating local control state
- the scheduler, generic listing/DEX owners and `market-notice-watch` share a cross-process nonblocking work lock. Lock contention is a network-0/DB-0 deferred no-op, and a separate process lock prevents duplicate schedulers
- each scheduled result is re-audited against the Build 69 one-intake/one-enrichment/one-score/max-one-case, pre-cutoff, Build 47, PAPER/order/Cloudflare/fitting safety envelope
- Build 70 counts event and asset-dedup p1h/p6h/p24h label coverage and keeps statistical validation blocked until every core window has at least 30 event labels and 20 unique-asset labels
- Build 71 is implemented as a read-only preregistered validator and reuses the exact Build 66 score snapshot passed through Build 70
- before Build 70 readiness, Build 71 returns `waiting_for_forward_sample`, `validation_statistics_calculated=false` and `statistics=null`; correlation/spread/late-half functions are not called
- after readiness, Build 71 calculates only the preregistered event/asset-dedup Spearman, top/bottom quartile spread, asset-dedup chronological late-half and strong-negative core checks
- the Build 65 primary level is `asset_dedup`; Build 72 is allowed only when every frozen criterion passes
- Build 71 remains PAPER/shadow/read-only. It does not fit weights, select a trade threshold, mutate the DB, publish Cloudflare data, change strategy/position sizing, wire PAPER A/B or place orders
- Windows HEAD `4f65082`에서 Build 71 contract/runtime PASS. Build 70은 0 event/0 unique asset, Build 71은 `waiting_for_forward_sample`, `validation_statistics_calculated=false`, `statistics=null`로 확인됨

Validation:
- Build 38 dedicated CI PASS
- Build 38 Windows runtime/PAPER self-heal/live official notice/Cloudflare publisher verification PASS
- Build 39 listing-history tests PASS
- Build 39 modular contract PASS
- Build 39 Cloudflare Pages typecheck PASS
- full B3 trader push and PR CI PASS with Build 39 source/supervisor changes
- Build 71 local full Python suite 255 tests, compileall, Build 65~71 contract chain and workflow YAML validation PASS
- Build 71 code commit `5c8081d` dedicated forward-validation CI PASS
- Build 71 code commit `5c8081d` full B3 trader CI PASS
- Build 71 Windows runtime at HEAD `4f65082`: contract PASS, Build 70 ledger PASS, Build 71 runtime PASS with no early statistics
- Build 69 scheduler local full Python suite 266 tests, server-off verifier, scheduler contract, Build 39/43 supervisor regression and Build 65~71 contract chain PASS
- Build 69 scheduler Windows runtime remains explicitly pending because the server is off; no process or network call was started for source validation
- Build 48 baseline through `8686fb8`: 28 GitHub Actions completed with no failure/queued/in-progress result
- Build 48 simple/detail + Records split latest-head CI/visual validation remains pending
- PR #1 remains Draft/unmerged

Immediate next action:
1. finish GitHub Actions for the latest Build 48 head, then perform desktop + phone screenshot QA of senior typography, holding plan, simple/detail toggle and Records split
2. add consistent non-color state cues after visual QA identifies the high-frequency surfaces that still rely on red/green alone
3. persist actual holding exchange in local holdings data; until then keep explicit user reference-exchange selection fail-safe
4. connect US macro/index/news context only through the existing Phase 5 data contract
5. leave the normal server on to let the 15-minute Build 69 process accumulate new official KRW listing samples automatically; manual Build 67 → 68 → 66 invocations are no longer the normal path
6. while Build 70 remains below 30 event/20 unique asset labels per core window, require Build 71 to stay `waiting_for_forward_sample` with no validation statistics
7. only a real Build 71 forward PASS may open Build 72 implementation; a FAIL means retire v2 or preregister a new hypothesis with a new forward cutoff, not tune v2 on the consumed validation sample

## Hard boundary

This workstream remains **PAPER-only**. Use forward-test evidence to find robust candidates before any later live-trading work. Do not add real-money order execution here.

## Runtime / local state

- Windows local PC, FastAPI/Uvicorn on port 8765
- secure launcher binds to `127.0.0.1`
- Cloudflare HTTPS phone access; no phone VPN dependency
- manual holdings/average prices/averaging plans remain in local SQLite
- user-added assets in `control/assets.json` must be preserved
- Telegram automatic delivery remains fresh BUY_CANDIDATE-only
- PR #1 stays Draft and must not be merged without explicit request

## Permanent UI baseline — Photo-eBook is canonical

Before modifying navigation, read the current Photo-eBook sources:
- `docs/spec-v1/06-liquid-navigation.md`
- `UI_REGRESSION_SPEC.md`
- `public/assets/js/ui/liquid-controller.js`
- `public/assets/styles/ui/liquid-skin.css`
- `public/assets/styles/desktop/nav-corrections.css`

Required Liquid contract:
- **one rail = one moving indicator = one nested skin = one controller**
- actual glass material belongs to the rail; shell/wrapper stays visually transparent
- moving indicator is a **direct child of the rail**
- indicator geometry uses active button `offsetLeft`, `offsetTop`, `offsetWidth`, `offsetHeight`
- active button/icon/text remains the real clickable element at a higher z-layer; never clone its content into the indicator and never hide the active button with `opacity:0`
- selected button paints blue only as a first-paint fallback; after controller ready, only the moving indicator paints blue
- approved Breeze easing: `cubic-bezier(0.34, 1.56, 0.64, 1)`
- browser owns native horizontal momentum; no JS `scrollLeft`/`scrollIntoView` loop and no custom pointer/touch pan for the nav rail
- PC top rail is `width:max-content`, centered on the actual chip group; never stretch a grey/glass rail across the viewport
- mobile rail keeps native Safari scrolling and approved safe-area behavior
- do not add a second navigation controller or a second moving indicator

Current implementation files:
- `dashboard/navigation-v3.js`
- `dashboard/navigation-v3.css`
- build marker: `UI 2026.08.24-8`

## Chrome freeze root cause and fix

The experimental `research-capital.js` used a broad `MutationObserver` on `document.body`. A mutation inside `#demoResearch` triggered `renderAggregate()`, which wrote `innerHTML` back inside `#demoResearch`, which could trigger the same observer again. With the full Bithumb universe this could form a high-frequency self-triggering DOM loop and freeze Chrome.

Current rule:
- no broad body MutationObserver for research decoration
- `research-capital.js` uses bounded 15-second data polling plus explicit coin-selection refresh only
- only write aggregate/detail DOM when the rendered value signature changed
- research assets load directly from `dashboard/index.html`; navigation code does not dynamically own research loading

## Browser / Git synchronization ownership

Do **not** reintroduce multiple sync/reload owners.

Current architecture:
- **one Git sync owner:** Python `GitAutoSync`
- `scripts/run-local.ps1` forces `AUTO_GIT_SYNC=true`, `AUTO_GIT_PUSH_CONTROL=true`, 15-second polling
- local `control/assets.json` and `control/runtime.json` are preserved while remote application code updates
- unexpected local code edits still fail closed
- dashboard-only file updates do not require Uvicorn restart
- `b3_trader/*.py` updates trigger supervised exit code 75 and automatic Python restart
- secure Cloudflare launcher no longer starts the experimental external `git-sync-watch.ps1`
- browser no longer force-reloads itself on every Git commit; user refresh is allowed and preferred over reload loops
- `dashboard/runtime-build.json` remains ignored so a stale experimental file cannot dirty/block the worktree

## Adaptive all-market PAPER research

- every valid Bithumb KRW market gets its own independent **10,000,000 KRW virtual account**
- accounts are isolated
- public Bithumb data only; no private/order endpoint
- roughly 3-minute full-market sweep
- `AssetStrategy` remains an input, but bounded `explore` / `idle_explore` entries prevent waiting forever for one legacy threshold
- staged additions, adaptive sizing, spread/slippage/BTC flash guards
- hard stop, dynamic take profit, trailing protection, market weakness and time/opportunity decay exits
- per-market adaptive profile changes are bounded DB parameters; Python source never self-modifies

## Research dashboard

Home:
- coin-by-coin 10M research status
- current return leader
- market count / scan progress / active positions / freshness

Results:
- full Bithumb KRW universe, scrollable and searchable
- filters: all / holding / completed-waiting / untraded / profit / loss
- sorts include return, position value, unrealized P/L, trade count, win rate, drawdown, opportunity and current price

Per-coin detail prioritizes:
- current price
- average entry
- current position value / weight
- realized and unrealized P/L
- next planned entry/add
- expected buy rounds
- dynamic target / stop / trailing protection
- market-memory history for later AI analysis
- fills and bounded learning feedback

Generated data remains local/ignored:
- `b3_trader/data/auto_demo.sqlite3`
- `dashboard/demo-runtime/KRW-XXX.json`

## Current verified viewer/publisher state

- Cloudflare snapshot/detail publishers are healthy after D1 retention/write-budget fixes.
- Snapshot retention is bounded and health exposes snapshot age/count.
- Current cadence is snapshot 60 seconds and market detail 300 seconds; unchanged detail rows are skipped and bounded batches protect D1 write budget.
- Viewer project-research completion count uses the same definition for numerator and unresolved count.
- Build 38 lifecycle/notice/timing/termination PAPER gate and PAPER self-heal are live-verified.
- Build 39 CEX listing-history foundation is source/CI complete; Windows live CEX data audit remains open.
- Build 69/70 Windows runtime is verified at 0 forward cases, and Build 71 source/CI/Windows runtime validation is complete; actual forward sample readiness is the current DEX v2 operational gate.
- Build 69 scheduled process is source-validated but its always-on Windows heartbeat is pending the next server start. Until then, the server-off verifier correctly reports `server_offline_runtime_pending` with network/DB 0.
- Current work must preserve PAPER scanning and publisher health while adding new features.

## Safety constraints

- PAPER-only
- no private Bithumb endpoints
- no live order placement
- manual real holdings remain display/calculator inputs only
- keep secrets/runtime DB/generated research data ignored/local
- no public direct exposure of port 8765
- live execution stays deferred to a separate future workstream


## Single-chat UI system audit checkpoint — CRYPTO-WO-20260921-001

Status: AUDIT COMPLETE / IMPLEMENTATION NOT STARTED.

Actual local recovery baseline supplied from the Windows checkout before documentation updates:
- branch: `b3-auto-trader-phase1`
- HEAD: `e9318be6c47877013e408d10479ea7f3e83f6506`
- tracked diff: clean
- staged diff: clean
- untracked: none
- upstream: `origin/b3-auto-trader-phase1`
- ahead/behind: `0 / 0`

The same code HEAD had already been deployed to Production Pages and the user confirmed the V17 asset changes appeared applied. GitHub CI readback for `e9318be6...` shows `B3 trader tests` and the returned Build 51~71 workflow set completed successfully. PR #1 remains Draft/open.

### UI system audit result

The primary problem is not missing features. It is propagation debt and competing information architecture:
- active shell exposes 6 top-level buttons plus system/account behind the user menu, while the permanent/product docs use several different conceptual groupings;
- Research, Assets, PAPER, Strategy, Sectors and Records each evolved their own search/filter/tab/master-detail grammar;
- `index.html` currently loads 37 CSS stylesheets. The loaded set totals about 260,399 CSS characters, 2,124 rule blocks, 100 media blocks and 1,874 `!important` declarations;
- late override ownership is concentrated in `strategy-native-v5.css`, `interaction-layout-v4.css`, `mainstream-v4.css`, `layout-fixes-v4.css`, plus subsequent viewport/compact/V17 layers;
- broad observer debt remains in `shared/rail-controls-v16.js`, which installs a document-root subtree `MutationObserver` contrary to AGENTS/MODULAR_ARCHITECTURE;
- the global simple/detail mechanism is directionally correct but is mainly CSS visibility gating, not yet a semantic per-page Primary/Supporting/Advanced composition contract.

Stable exemplar candidates to preserve:
- Strategy V5 master rail + selected-strategy workspace + internal views;
- Records audience split: `내 매매·판단` vs `시스템·학습`;
- Research master/detail with local live patches;
- Assets V17 position hero → facts → holdings editor handoff;
- `shared/ui-continuity.js` and scoped V16 live-patch ownership;
- `shared/viewport-handoff-v4.js` explicit mobile return-to-list behavior.

Target IA for the next design-system waves, with no capability deletion:
- global: `홈 / 코인 / 내 자산 / 모의투자 / 기록 / 더보기`;
- Coin local navigation: `코인 / 시장현황 / 테마`;
- Paper local navigation: overall performance / per-coin / method-strategy comparison / current execution;
- More: system / account / operations.

Target disclosure order on primary operational pages:
`지금 무엇을 해야 하는가 → 현재 가격·보유·손익 → 왜 그런 판단인가 → 다음 행동 → 고급 분석·근거`.

### External read-only skill evidence used in the audit

- `hueyexe/frontend-agent-skills@2841c079dd8a9c634882227194dc42e25227710d`, MIT: IA/navigation, usability, design-system architecture, interaction patterns, visual hierarchy, accessibility. Adopted task-first IA, labels-as-promises, progressive disclosure, low-specificity token/component ownership, stable wayfinding, semantic/native accessibility. Overridden where project-native DESIGN/TASTES require denser financial presentation and localStorage-based private Viewer state instead of URL-shareable state.
- `educlopez/ui-craft@ceecc8e1fb0c2befda73da996435900d6dd0c1ac`, MIT: audit/system extraction and dense-dashboard anti-slop. Adopted tabular numerals, operator-density, no decorative chart/card grid. Did not adopt its generic style as a theme.
- `emilkowalski/skills@85e8e2363b713506e1d5b6e07a0eb2da66be1bc3`, MIT: mobile-native checks. Adopted 16px focused input minimum, safe-area, capability media queries, touch feedback, real-device QA. Design-engineering polish is deferred until structure stabilizes.
- `microsoft/skills@14655200e871a89c013803b3aa4d88202cb03fc1`, MIT: used only as final review rubric for frictionless action, craft, accessibility and trustworthy errors. Creative-font/gradient/background guidance is rejected where it conflicts with CRYPTO DESIGN/TASTES/system-font/no-decoration rules.

### Exact next gate

Do not begin a broad rewrite. Review/approve the audit, then create/activate `CRYPTO-WO-20260921-002` with a bounded foundation scope:
1. remove the broad `rail-controls-v16.js` MutationObserver and move enhancements to explicit render/ui:refresh ownership;
2. establish one canonical token/control/master-detail foundation and regression contract;
3. migrate only the shared shell/high-frequency primitives first;
4. no trading/data/PAPER semantic change, no feature deletion, no Production deploy until visual/regression QA passes.

Because this HANDOFF/TASKS update is a documentation-only Git mutation performed through GitHub after the local readback, the user's local checkout will need a fast-forward before the next implementation work begins.


## CRYPTO-WO-20260921-002 UI foundation consolidation — VERIFY

Current implementation HEAD: `3e15a8d8a1959a99f7a2a8c5ff7196d83571c7a9`.

Implementation/verification result:
- broad document-root rail `MutationObserver` removed;
- rail controls use explicit root-scoped render/`ui:refresh` lifecycle;
- canonical UI geometry tokens live in `tokens.css`;
- shell/components/interaction layer consume the canonical tokens;
- additive shared composition primitives and `UI_FOUNDATION_CONTRACT.md` added;
- V18 regression checker is part of `npm run typecheck`;
- no trading/data/PAPER/SQLite/real-money semantic change;
- no Production deployment.

Actual local readback at `3e15a8d...`:
- branch `b3-auto-trader-phase1`;
- tracked/staged/untracked = 0/0/0;
- upstream aligned = 0/0;
- full `npm run typecheck` PASS through `V16_HOLDINGS_WRITE=PASS` and `[PASS] CRYPTO WO-002 LOCAL FOUNDATION VERIFY`.

Latest GitHub CI at the same HEAD:
- B3 trader tests run 2750 = SUCCESS;
- python-test = SUCCESS;
- cloudflare-typecheck = SUCCESS;
- cloudflare-pages-viewer = SUCCESS, including Viewer baseline source contract;
- dashboard-smoke = SUCCESS;
- returned Build 51~71 workflow set = SUCCESS.

Next gate is visual QA only. Use a non-Production preview deployment of this exact HEAD, then verify representative desktop/tablet/phone widths, light/dark, keyboard/focus, simple/detail reader mode, selection/search/sort continuity, and live-polling continuity. Do not deploy Production until this gate is accepted.


### WO-002 preview deployment checkpoint

Preview source: `7e19da175c34fc4e6b172581ebf2831bd5426a67` (implementation `3e15a8d...` plus docs-only durable commits).

Preview URLs:
- deployment: `https://1072960d.crypto-paper-viewer-ydh1121-cf36.pages.dev`
- alias: `https://qa-v18-ui-foundation.crypto-paper-viewer-ydh1121-cf36.pages.dev`

Production was not deployed. Visual QA must use this preview only and must avoid holdings/runtime write actions. Start with 1440px dark on Home / Coin / Assets / Paper / Strategy / Records, then 390px dark on Coin / Assets / Paper, followed by light mode, keyboard/focus, simple/detail, selection/search/sort, and live-polling continuity.


### WO-002 partial desktop visual-QA handoff — 2026-09-21

User stopped screenshot submission after the current desktop sweep; implementation/QA work continues. Treat the supplied screenshots as a durable partial-QA checkpoint, not acceptance.

Observed preserve candidates:
- Assets V17 hierarchy remains the clearest operational page.
- Strategy master/detail selection rail and internal tabs remain intact.
- Records keeps the useful user-vs-system audience split.
- Research/market selection rails and scoped detail surfaces remain functional in the screenshots.

Observed repair candidates for later bounded waves:
1. Market overview/dashboard still has card-soup pressure and competing visual prominence.
2. Theme/Sectors has excessive simultaneous density (ranking rail + coin table + evidence panel) and small scanning text.
3. PAPER/Strategy tabs show large empty detail areas when content is sparse, causing inconsistent vertical rhythm.
4. Sticky global/local header stack needs explicit scroll/focus visibility QA; long-page screenshots show content tight to the sticky boundary.
5. System is operationally useful but visually flat: many equal-weight sections/status rows with weak prioritization.

Continue bounded WO-002 QA/foundation repair from these findings. Production remains prohibited; page-level redesign beyond WO-002 foundation scope belongs to a later bounded work order.


### WO-002 bounded desktop foundation repair

Work continues after the desktop screenshot sweep. Two foundation-level issues were repaired without changing page semantics:

1. Sticky-shell focus/anchor visibility: `viewport-first-v9.css` now sets document `scroll-padding-top` from the responsive `--shell-header-offset`, with regression coverage.
2. System desktop hierarchy: retired the old `mainstream-v4.css` one-column override so `records-system.css` again owns the intended 3/2/1 responsive operations grid and 2/1 system summary grid.

These are override/foundation repairs, not the later page-level hierarchy redesign for Market/Theme/PAPER/Strategy. Latest regression verification and Preview re-deploy are still required. Production remains unchanged.


## CRYPTO-WO-20260921-003 Market + Theme page hierarchy — IMPLEMENTED / VERIFY

The V18 foundation wave is no longer being expanded. WO-003 uses the user's supplied desktop screenshots as the page-level evidence source and touches only Market dashboard + Theme/Sectors hierarchy.

Implemented:
- Market dashboard now has deliberate prominence: market state is primary; actual-assets/PAPER are supporting; watch list is primary intelligence; sector/strategy are supporting.
- Theme/Sectors no longer presents rank + coin table + project profile as three simultaneous desktop rails. Rank + selected-theme detail remain primary, while project evidence moves below the table behind native progressive disclosure and automatically opens on explicit coin selection.
- No new cards/tabs/chips were added. Data selectors, market/sector data, PAPER/trading logic, SQLite semantics and real-money boundary are unchanged.
- A dedicated V19 regression contract protects cache lineage, dashboard prominence, two-pane Theme ownership, and project-evidence accessibility.

Source implementation lineage through `ff9253e2c174a8cc5c2f6d77618568c7c5185a89`; documentation commits follow on the same branch. Next gate is exact latest-head CI, then actual local fast-forward/typecheck, then Preview-only redeploy. Production remains prohibited.


### WO-003 exact-head remote CI gate

Remote HEAD `deb3c30385cdcf86604a62a9357c490a6071b522` is unchanged and exact-head CI is green:
- B3 trader tests #2800 = SUCCESS
- dashboard-smoke = SUCCESS
- cloudflare-typecheck = SUCCESS
- python-test = SUCCESS
- cloudflare-pages-viewer = SUCCESS
- returned Build 51~71 workflow set = SUCCESS

Next gate is actual local fast-forward to this exact HEAD, clean/aligned readback, full `npm run typecheck`, then Preview-only redeploy/readback on `qa-v18-ui-foundation`. Production remains prohibited.


### WO-003 acceptance

WO-003 is ACCEPTED.

Actual local/current verification:
- `b3-auto-trader-phase1` at `7e29f78a7a20009fe741b35756cf38d2cdc96fef`;
- tracked/staged/untracked = 0/0/0;
- upstream = 0/0;
- full Viewer contract PASS, including `PAGE_HIERARCHY_V19=PASS`.

Preview verification:
- deployment `14c1a46b.crypto-paper-viewer-ydh1121-cf36.pages.dev`;
- alias `qa-v18-ui-foundation.crypto-paper-viewer-ydh1121-cf36.pages.dev`;
- Market hierarchy asset live;
- Theme hierarchy asset live;
- Production not deployed.

Close WO-003 here. Do not fold PAPER/Strategy sparse-detail composition into this work order; open a new bounded WO.


## CRYPTO-WO-20260921-004 PAPER + Strategy sparse-detail hierarchy — IMPLEMENTED / VERIFY

Implementation head: `c8c13dfa4aa0b175c3d7f58bb92eb17dfb8c3515`.

Changes are composition-only:
- PAPER no longer reserves a full viewport-height workspace when the selected detail is short. The master rail is still bounded and scrollable, but the detail pane follows its actual content height.
- Strategy no longer uses a fixed 440px detail minimum or a second vertical scroll container. Local tabs keep the same content and semantics while the visible panel determines height.
- Sticky geometry follows `--shell-header-offset` so the master/detail arrangement remains compatible with the V18 shell contract.
- No PAPER execution semantics, strategy semantics, data contracts, SQLite behavior, holdings writes, or real-money boundaries changed.

Regression contract `SPARSE_DETAIL_V20` is wired into the Viewer typecheck. Next gate is exact-head CI, then local reproduction and Preview-only deploy. Production remains prohibited.


### WO-004 exact-current CI gate

The first implementation-head B3 test run was superseded/cancelled by subsequent docs-only commits. The exact current branch head `9f598c70bd3a18c5af2160dc05a721504d01e1fd` contains the same WO-004 code (only TASKS/HANDOFF differ from `c8c13dfa4...`) and has green CI:
- B3 trader tests #2819 = SUCCESS
- returned Build 51~71 workflow set = SUCCESS

Next gate: actual local fast-forward to the latest durable head, clean/upstream readback, full `npm run typecheck` including `SPARSE_DETAIL_V20=PASS`, then Preview-only redeploy/readback. Production remains prohibited.


### WO-004 acceptance

WO-004 is ACCEPTED.

Actual local/current verification at `b72ef6424121431562d53bd0c1e5351b184db90a`:
- tracked/staged/untracked = 0/0/0;
- upstream = 0/0;
- full Viewer contract PASS including `SPARSE_DETAIL_V20=PASS`.

Preview verification:
- deployment `9d55cef5.crypto-paper-viewer-ydh1121-cf36.pages.dev`;
- alias `qa-v18-ui-foundation.crypto-paper-viewer-ydh1121-cf36.pages.dev`;
- PAPER content-height repair LIVE;
- Strategy sparse-detail repair LIVE;
- Production not deployed.


## CRYPTO-WO-20260921-005 Mobile & interaction continuity — IMPLEMENTED / VERIFY

Source changes:
- shell horizontal/top/bottom safe-area ownership;
- 100dvh fallback for app/auth surfaces;
- 360-safe three-column main nav with text containment;
- canonical 44px compact primary control height;
- safe-area-aware auth theme toggle and journey rail;
- V21 regression contract covering native zoom, coarse-pointer 16px inputs, focus/selection/scroll restore, snapshot-live patch ownership and durable search/filter/selection state.

No new navigation controller, polling owner, page IA, trading semantics or Production deployment was introduced.

Next gate: exact-head CI, then actual local fast-forward/typecheck including `MOBILE_INTERACTION_V21=PASS`, then Preview-only redeploy/readback. Real iPhone Safari device QA remains a final acceptance gate after source-level contracts pass.


### WO-005 exact-head CI gate

Exact code head `3acfe9367629d3ed69bec48b069bfcb7211c4c17` is green:
- B3 trader tests #2853 = SUCCESS
- cloudflare-pages-viewer = SUCCESS
- cloudflare-typecheck = SUCCESS
- python-test = SUCCESS
- dashboard-smoke = SUCCESS
- returned Build 51~71 workflow set = SUCCESS

Two CI failures during this wave were stale contract assertions, not product regressions: the IA checker still expected pre-safe-area literal padding, and the V18/mainstream checks still expected old cache keys / extra late overrides. The repair kept `interaction-layout-v4.css` at the existing 400-`!important` ceiling by moving mobile touch sizing into canonical tokens and owning theme/journey rules.

Next gate: actual local fast-forward to the latest durable docs head, clean/upstream 0/0 readback, full Viewer typecheck including `MOBILE_INTERACTION_V21=PASS`, then Preview-only deploy/readback. Production remains prohibited.


### WO-005 acceptance

WO-005 is ACCEPTED at source/Preview level.

Actual local/current verification:
- branch `b3-auto-trader-phase1` @ `c841bf49bda6b8ddb7fa7d46ca3a147324e0bbb3`;
- tracked/staged/untracked = 0/0/0;
- upstream = 0/0;
- full Viewer contract PASS including `MOBILE_INTERACTION_V21=PASS`.

Preview verification:
- deployment `c476bcbe.crypto-paper-viewer-ydh1121-cf36.pages.dev`;
- alias `qa-v18-ui-foundation.crypto-paper-viewer-ydh1121-cf36.pages.dev`;
- MOBILE SAFE-AREA ASSETS LIVE;
- MOBILE TOUCH GEOMETRY LIVE;
- Production not deployed.


## CRYPTO-WO-20260921-006 Final device interaction QA — ACTIVE

This is a verification-only work order. Do not mutate source merely to make the checklist pass.

Primary gate: 390px. Secondary gates: 430px and 360px. Device-specific gate: real iPhone Safari for focus zoom, software keyboard and safe-area behavior.

Continuity checks must include:
- select coin/holding/PAPER/strategy, scroll into detail, wait through at least one live polling cycle, confirm selection and scroll remain;
- type in search/filter input, keep focus, wait through polling, confirm value/caret/focus remain;
- open a disclosure/details block, wait through polling, confirm it stays open;
- switch simple/detail and light/dark at compact width and confirm layout does not jump into horizontal page overflow.

Any defect must be reproduced before opening a bounded repair WO. Production remains prohibited.


## CRYPTO-WO-20260921-007 Simplified trading IA rebaseline — ACTIVE

The previous broad page tree was rejected as over-expanded and likely to recreate the same UX failure.

Canonical primary destinations are now:
- 실전매매: exchange/ticker/current price → dominant strategy → split entry/exit/weight → averaging/profit calculators → evidence-backed likely-riser shortlist.
- 가상매매: selected coin → strategy tabs with account/trade history → BTC/ETH-relative movement → news/indicator/event reaction.

Everything else is secondary and must be classified under 탐색, 연구/데이터, 기록 or 운영. Do not resume device QA or cosmetic repair as current WIP. First produce the exhaustive mapping table of already-developed capabilities into this simplified structure.

Production remains prohibited.


### WO-007 planning checkpoint — capability map + Low-fi ready

Planning artifacts are ready for user review:
- `docs/workstreams/dashboard-v1/EXISTING_CAPABILITY_CANONICAL_MAPPING_V1.md` — 100 existing/future capabilities mapped to canonical destinations and treatment.
- `docs/workstreams/dashboard-v1/SIMPLIFIED_TRADING_LOWFI_SPEC_V1.md` — only two primary user pages: 실전매매 / 가상매매.

The Low-fi deliberately removes the generic Home/dashboard as a required primary destination. 실전매매 contains selector → dominant strategy → split entry/exit/weights → averaging/profit calculator → compact rising-candidate list. 가상매매 keeps the selected coin context and switches only among 전략 / BTC·ETH / 이벤트.

Reference translation:
- CODE1 Harness = flow/IA discipline, flat scan, anti-card nesting, context preservation.
- openexch/trading-ui = persistent instrument context + adjacent task surfaces, not its live-order semantics.
- swiss-style-theme = dense grid/alignment/hairline hierarchy.
- frontend-art-direction = real data before decorative dashboard polish.
- Carbon = dense table/state/accessibility reference.

Do not begin source migration until the user accepts or edits this hierarchy. Production remains prohibited.


## CRYPTO-WO-20260921-008 — READY / WAITING_LOCAL_PARENT_VERIFY

User continuation released the WO-007 review gate.

Migration authority: `SIMPLIFIED_TRADING_MIGRATION_PLAN_V1.md`.

First bounded implementation is only primary shell + 실전매매 v1. It may reuse existing real data and calculators but must not delete old routes, change PAPER/strategy semantics, invent dominant strategy evidence, change holdings mutation behavior, or add live order submission.

Before any source mutation, actual local must be fast-forwarded to the new durable head and prove branch `b3-auto-trader-phase1`, tracked/staged/untracked 0, upstream 0/0.

Production remains prohibited.


## CRYPTO-WO-20260921-008 — IMPLEMENTED / VERIFY_LOCAL_AND_PREVIEW

Implementation code head: `169ca445ef4a93103fc548f642bacc5de675a77b`.

What changed:
- added primary `live` route and `live-trading.js`;
- primary nav is now 실전매매 / 가상매매 / 탐색 / 기록;
- legacy Assets remains under 실전매매 journey; Strategy remains under 가상매매 journey; Market/Theme remain under 탐색;
- selected live context persists `liveExchange/liveMarket/liveCalculator`;
- current actual holding, current quote, observation candidates, current PAPER plan, strategy-lab per-coin results, averaging calculator and profit calculator are composed on one page;
- missing strategy-specific split targets/weights remain explicit projection gaps rather than fabricated values;
- `live` polling refreshes data-owned surfaces while calculator input state stays untouched.

Exact-head CI is green:
- B3 trader tests #2925 SUCCESS
- cloudflare-pages-viewer SUCCESS
- cloudflare-typecheck SUCCESS
- python-test SUCCESS
- dashboard-smoke SUCCESS
- returned Build 51~71 set SUCCESS

Next gate is actual-local fast-forward to the durable docs head, full `npm run typecheck` requiring `SIMPLIFIED_TRADING_V22=PASS`, then Preview-only deploy/readback and focused visual QA. Production remains prohibited.


### WO-008 source/contract/preview verification

Source/contract/Preview verification is complete.

- actual local/current: `ba3c59a50962ae1a5bdc41053a75f9e6bf9e1ec7`, clean 0/0 and upstream 0/0
- full Viewer typecheck PASS including `SIMPLIFIED_TRADING_V22=PASS`
- Preview deployment: `f18a2c1a.crypto-paper-viewer-ydh1121-cf36.pages.dev`
- stable alias: `qa-v18-ui-foundation.crypto-paper-viewer-ydh1121-cf36.pages.dev`
- raw UTF-8 readback PASS on both immutable deployment and alias for all live-trading markers
- Production not deployed

The earlier `Invoke-WebRequest` Korean-marker failure was a Windows PowerShell decoding false negative, not a missing asset. Do not redeploy for that issue.

Only focused visual acceptance remains for WO-008: one desktop and one 390px screenshot of the new `실전매매` page. Do not reopen broad screenshot sweeps.
