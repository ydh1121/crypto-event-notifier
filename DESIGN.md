# Crypto Auto Trader design system

This document defines the dashboard's permanent visual and interaction baseline.

It is distilled from the user's approved Photo-eBook UI and selected public design references. It is a project-specific spec, not a copy of another product.

For UI behavior and Korean copy, the current Photo-eBook `UI_REGRESSION_SPEC.md` and `docs/spec-v1/20-korean-copywriting-skill.md` are approved reference contracts. Adapt their proven rules to this dashboard; do not copy photography-specific content.

## 1. Product character

The dashboard is an operational trading console, not a marketing landing page.

It should feel calm, precise, native, and expensive without looking decorative. The interface must make market state, risk, holdings, and next action legible within seconds.

Visual priority:

1. what the user should do now: buy candidate / wait / do not buy
2. actual manually entered holdings, average price, value and P/L
3. watched assets and decision state
4. market context and score history
5. paper-forward-test performance
6. recent fills/events
7. settings and maintenance

If an element does not help a decision, reduce its visual weight or move it behind details/settings.

## 2. Foundation tokens

Use system fonts only. Do not ship font files.

```css
--accent: #2f63d6;
--accent-pressed: #2858c1;
--accent-soft: #eaf1ff;
--ink: #1d1d1f;
--text: #343437;
--secondary: #68686d;
--tertiary: #8e8e93;
--canvas: #ffffff;
--grouped: #f5f5f7;
--grouped-2: #ececf1;
--success: #267a3f;
--success-soft: #e8f5eb;
--warning: #8a6500;
--warning-soft: #fff3d7;
--danger: #9b2c28;
--danger-soft: #fbe9e7;
--border: rgba(0,0,0,.075);
--card: rgba(255,255,255,.97);
--shadow-soft: 0 7px 18px rgba(20,30,55,.055);
--shadow: 0 10px 30px rgba(20,30,55,.08);
--r-sm: 12px;
--r-md: 18px;
--r-lg: 26px;
--pill: 999px;
```

Structural spacing uses 8/12/16/20/24/32/48. Small optical corrections may use 2/4/6 px. Avoid arbitrary spacing unless a specific geometry needs it.

## 3. Typography

Font stack:

`-apple-system, BlinkMacSystemFont, "SF Pro Text", "Apple SD Gothic Neo", "Noto Sans KR", "Segoe UI", system-ui, sans-serif`

Use strong typography sparingly.

- app title: 21–24 px / 700
- page section: 24–30 px / 720
- card title: 17–20 px / 680
- KPI: 24–34 px / 700 depending on density
- body: 14–16 px
- metadata: 11–13 px

Korean body copy uses `word-break: keep-all` and sensible line lengths. Do not force every label into uppercase. English micro labels may use restrained letter spacing.

On iPhone/iOS Safari, every form control that can receive focus must render at **16 px or larger**. Do not solve field density by shrinking form text below 16 px because Safari will zoom the page on focus.

## 4. Layout

Desktop content width: approximately 1180–1280 px centered with 24 px gutters.

Mobile: one continuous column with 14–16 px gutters plus safe-area padding.

Use a sticky top shell with a translucent neutral surface. Avoid a heavy solid header bar.

Desktop may use a two-column workspace where the left side carries market/asset analysis and the right side carries system/event detail. Do not reduce primary content to narrow centered cards with large empty right-side space.

Cards use grouped-canvas separation first, borders second, shadows last. Avoid stacking strong border + strong shadow + tinted background on the same card.

Repeated card collections must have stable geometry. Optional data such as `내 평단` must use a placeholder row or reserved internal slot instead of making one card much shorter than its neighbors. Equal-height grid rows must stretch cleanly without forcing excessive empty whitespace.

## 5. Navigation

Top-level user labels are short and ordinary Korean:

- 홈
- 코인
- 결과
- 기록
- 설정

One selected state only. Do not render a second active background inside an already-selected indicator.

On mobile, use native scrolling/interaction ownership. Do not replace native touch scrolling with custom pointer handling unless a specific control requires it.

## 6. Status hierarchy

Operational state must be immediately readable without relying only on color.

Examples:

- `정상 감시`
- `새 매수 잠시 멈춤`
- `긴급 정지`
- `텔레그램 연결됨`
- `백업 대기/완료/오류`

Danger is reserved for actual destructive/risk states. Do not use red merely because a market return is negative if that makes system danger ambiguous.

## 7. Asset cards

The default asset card should expose only what is useful at a glance:

- ticker
- current price
- current decision in ordinary Korean (`조금 더 지켜보기`, `가격이 내려오길 기다림`, `매수 후보`, `지금은 매수하지 않음`, `확인 필요`)
- one short reason sentence
- manually entered average price and current P/L when present; a stable placeholder when absent
- `시장` and `타이밍` with both grade and 0–100 value

Relative strength, Fibonacci/pullback, orderbook balance, volatility and other technical inputs belong under `판단 근거 자세히 보기`, not the default card.

Internal codes such as `WATCH`, `WAIT_PULLBACK`, `BUY_CANDIDATE`, `RISK_OFF`, `Regime`, `Entry`, and `Context` remain valid implementation vocabulary but must not be the primary user-facing wording.

Score visuals use horizontal tracks or compact gauges; not oversized circular gauges.

## 8. Charts

Charts exist to answer questions, not to decorate.

Required charts:

1. price history with paper buy/sell markers
2. market-condition and buy-timing history on the same time axis
3. portfolio equity curve
4. optional exposure/drawdown history

Chart rules:

- no 3D, gradient area fills, glow, or rainbow series
- gridlines subtle and sparse
- axes only when they add meaning
- use the primary accent for price/equity; use a second restrained neutral/amber for entry quality where necessary
- buy/sell markers distinguishable by shape/text as well as color
- charts support 1H / 6H / 24H / 7D when enough data exists
- empty states explain that data is still being collected

Prefer a dependency-light SVG/canvas implementation. Do not add a large chart library unless interaction requirements justify it.

## 9. Motion and live refresh

Motion should preserve continuity and indicate state.

- hover/press: 120–180 ms
- sheets/dialogs: 180–260 ms ease-out or spring-like curve
- tab/segment movement: smooth, no overshoot that clips at edges
- numeric live updates: no constant counting animations
- charts may transition subtly when changing range; no animation on every 5-second refresh

Respect `prefers-reduced-motion`.

**Live polling must preserve deliberate UI state.** A 5-second data refresh must not collapse an open `details`, reset the selected range/tab, discard form input, steal focus, jump scroll position, or otherwise behave like a page reload. Preserve state before rerender or patch only the data nodes that changed.

## 10. Mobile and phone-control behavior

The phone view is a real control surface, not a read-only miniature desktop.

- touch targets generally >= 44 px; routine form controls target 46–48 px
- safe bottom padding for browser chrome/home indicator
- no horizontal document overflow
- destructive controls are not adjacent to routine controls without spacing/confirmation
- button labels stay on one line; shrink/reflow the container before wrapping button text
- chart panels can horizontally pan internally only when necessary
- connection settings use the user-facing name `휴대폰 연결 코드`; the implementation may continue to call it a dashboard token internally
- the connection code may be revealed on the loopback PC UI, but remote clients must never receive it from an unauthenticated endpoint

External phone access uses **HTTPS Cloudflare Tunnel** to a loopback-only local service. Prefer a persistent named Tunnel + custom hostname after one-time setup, so server restarts keep the same phone URL and browser localStorage. Quick Tunnel is a temporary fallback only. Never instruct users to expose port 8765 directly to the internet.

A loopback-only onboarding convenience may generate a one-time link whose connection code exists only in the URL fragment (`#connect=...`). The remote page must import it into localStorage and immediately remove the fragment from the address bar. Never put the code in a query parameter/path or server log.

## 11. Forms, buttons and dialogs

Routine settings should be grouped by meaning rather than displayed as one dense input matrix.

Suggested groups:

- 주문/포지션
- 매수 판단 기준
- 자동으로 매수를 막는 조건
- 알림/동기화

Use bottom sheets on small screens and centered dialogs on desktop when practical.

Saved secrets are never echoed back. Display only `설정됨` / masked state, except the local-PC-only phone connection code described above.

Buttons use short Korean action labels. Default rule: **one button = one line**. If text wraps at a supported width, change grid/flex allocation or shorten the label; do not accept a two-line button as normal.

Forms must remain stable while background data refreshes. Do not rerender an actively edited calculator row just because market data polled again.

## 12. Korean copy and beginner comprehension

Before adding or materially rewriting Korean UI copy, read the Photo-eBook `docs/spec-v1/20-korean-copywriting-skill.md` and apply its current project-approved rules. The user's direct wording and before/after feedback outrank generic guidance.

The default dashboard must be understandable to a non-trader older adult without a glossary. Review standard: **a Korean user in their 60s who has never heard Regime, Entry, Context, risk-off, drawdown, profit factor, spread, slippage, or bps should still understand what the screen is telling them to do.**

Every primary state must answer three questions in ordinary Korean:

1. 지금 사는 쪽인가, 기다리는 쪽인가?
2. 왜 그렇게 판단했나?
3. 내가 가지고 있다면 평단과 손익은 어떤가?

Required score wording:

- Regime → `전체 시장 분위기`
- Entry → `지금 매수 타이밍`
- Context → `비슷한 코인들의 흐름`
- RISK_OFF → `지금은 매수하지 않음`
- WAIT_PULLBACK → `가격이 내려오길 기다림`
- WATCH → `조금 더 지켜보기`
- PAPER → `가상매매`
- drawdown / DD → `하락폭`
- realized PnL → `확정 손익`
- Profit Factor → `번 돈 ÷ 잃은 돈`
- Dashboard token → `휴대폰 연결 코드`

Score values must not appear alone. Display a plain-language grade beside the number:

- 0–39: `매우 나쁨`
- 40–54: `좋지 않음`
- 55–64: `보통`
- 65–74: `좋음`
- 75–100: `매우 좋음`

Technical terminology may remain under `판단 근거 자세히 보기`, advanced settings, logs, or developer-facing files. The top-level dashboard and Telegram alerts use ordinary Korean first.

Prefer short, concrete copy such as:

- `지금은 새로 사지 않는 편이 낫습니다.`
- `시장 분위기는 괜찮지만 현재 가격은 서둘러 살 자리가 아닙니다.`
- `매수 후보가 되면 알림을 보냅니다.`

Avoid:

- bare `RISK_OFF`, `Regime 49.62`, `Entry 52.23`, `Context 48.2`
- long explanatory AI prose inside cards
- repetitive `~을 봅니다`, `~을 확인합니다`, `~할 수 있습니다`
- translated nouns such as `실행 가능성`, `전략적 함의`
- defensive `~이 아니다. ~이다.` patterns without need
- inconsistent terminology for the same action

## 13. Telegram policy

Current approved automatic Telegram policy is intentionally quiet:

- send when a watched coin **newly enters BUY_CANDIDATE**
- include current price and recommended entry amount/percentage
- do not send WAIT/RISK_OFF state changes, routine fills, Git sync, backup, program start/stop, daily summary, or routine errors unless the user explicitly changes the policy
- manual Telegram test remains available from settings
- repeated BUY_CANDIDATE alerts use cooldown/state transition logic to avoid spam

## 14. Market-reference rules

`ETH/BTC` is a market-reference signal, not a tradeable KRW asset in the current engine.

- derive ETH/BTC ratio from ETH-KRW and BTC-KRW prices
- derive 24h ETH/BTC relative change from ETH and BTC returns
- show plain meaning such as `ETH가 더 강함`, `BTC가 더 강함`, or `비슷한 흐름`
- if the user types `ETH/BTC` in the ticker add box, explain that it is already monitored as a market reference instead of returning an unsupported-market error

## 15. Regression rules

- Do not change unrelated mobile geometry while fixing desktop.
- Do not introduce a second owner for the same selected/scroll state.
- Do not make live polling trigger layout shifts or reset interactive state.
- Open disclosures stay open across polling until the user closes them or changes asset.
- iOS form inputs stay >=16 px on focusable controls.
- Button labels do not wrap at supported widths.
- Repeated cards maintain stable height/row geometry when optional holding data is absent.
- Do not hide system errors merely to keep the dashboard visually clean; keep them in records/settings even if Telegram is quiet.
- Do not make a graph look complete when there is insufficient history; show the data-collection state.
- Do not expose secrets to Git, Drive, Telegram, chart payloads, query strings, or server logs.
- The only allowed browser-URL secret exception is a loopback-generated, one-time `#fragment` onboarding link that is immediately cleared after localStorage import.
