# Crypto Auto Trader design system

This document defines the dashboard's permanent visual and interaction baseline.

It is distilled from the user's approved Photo-eBook UI and selected public design references. It is a project-specific spec, not a copy of another product.

## 1. Product character

The dashboard is an operational trading console, not a marketing landing page.

It should feel calm, precise, native, and expensive without looking decorative. The interface must make market state, risk, and system health legible within seconds.

Visual priority:

1. current risk/system status
2. portfolio/PAPER performance
3. watched assets and decision state
4. market/score history
5. recent fills/events
6. settings and maintenance

If an element does not help a decision, reduce its visual weight or remove it.

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

Structural spacing uses 8/12/16/20/24/32/48. Small optical corrections may use 2/4/6 px. Avoid arbitrary 13/19/27 px spacing unless a specific geometry needs it.

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

## 4. Layout

Desktop content width: approximately 1180–1280 px centered with 24 px gutters.

Mobile: one continuous column with 14–16 px gutters plus safe-area padding.

Use a sticky top shell with a translucent neutral surface. Avoid a heavy solid header bar.

Desktop may use a two-column workspace where the left side carries market/asset analysis and the right side carries system/event detail. Do not reduce primary content to narrow centered cards with large empty right-side space.

Cards use grouped-canvas separation first, borders second, shadows last. Avoid stacking strong border + strong shadow + tinted background on the same card.

## 5. Navigation

Use a compact pill/segment rail for top-level dashboard views:

- 개요
- 자산
- 성과
- 활동
- 설정

One moving/selected state only. Do not render a second active background inside an already-selected indicator.

On mobile the rail may scroll horizontally using native `overflow-x:auto`; do not replace native touch scrolling with custom pointer handling.

## 6. Status hierarchy

Operational state must be immediately readable without relying only on color.

Examples:

- `정상 감시` + neutral/success indicator
- `새 매수 잠시 멈춤`
- `긴급 정지`
- `Telegram 연결`
- `GitHub 최신`
- `백업 대기/완료/오류`

Danger is reserved for actual destructive/risk states. Do not use red merely because a market return is negative if that makes system danger ambiguous.

## 7. Asset cards

An asset card should expose:

- ticker / market
- current decision in ordinary Korean (`조금 더 지켜보기`, `가격이 내려오길 기다림`, `매수 후보`, `지금은 매수하지 않음`, `확인 필요`)
- price and recent change
- `시장 분위기`, `매수 타이밍`, and related-market condition with both a 0–100 value and a plain-language grade
- relative strength, pullback, orderbook balance only as secondary detail
- position/average/value when present
- a small 24h/selected-window sparkline

Internal codes such as `WATCH`, `WAIT_PULLBACK`, `BUY_CANDIDATE`, `RISK_OFF`, `Regime`, `Entry`, and `Context` remain valid implementation vocabulary but must not be the primary user-facing wording.

Score visuals use horizontal tracks or compact gauges; not oversized circular gauges.

A card click/expand reveals technical detail rather than placing every metric on the default surface.

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
- buy/sell markers must remain distinguishable by shape/text as well as color
- charts should support 1H / 6H / 24H / 7D windows when enough data exists
- empty states explain that data is still being collected

Prefer a dependency-light SVG/canvas implementation. Do not add a large chart library unless interaction requirements justify it.

## 9. Motion

Motion should preserve continuity and indicate state.

- hover/press: 120–180 ms
- sheets/dialogs: 180–260 ms ease-out or spring-like curve
- tab/segment movement: smooth, no overshoot that clips at edges
- numeric live updates: no constant counting animations
- charts may transition subtly when changing range; no animation on every 5-second refresh

Respect `prefers-reduced-motion`.

## 10. Mobile and phone-control behavior

The phone view is a real control surface, not a read-only miniature desktop.

- touch targets generally >= 44 px
- safe bottom padding for browser chrome/home indicator
- no horizontal document overflow
- destructive controls are not adjacent to routine controls without spacing/confirmation
- chart panels can horizontally pan internally only when necessary
- connection settings use the user-facing name `휴대폰 연결 코드`; the implementation may continue to call it a dashboard token internally
- the connection code may be revealed on the loopback PC UI, but remote clients must never receive it from an unauthenticated endpoint

External access uses Tailscale or trusted LAN. Never instruct users to expose port 8765 directly to the internet.

## 11. Forms and dialogs

Routine settings should be grouped by meaning rather than displayed as one dense 10-input matrix.

Suggested groups:

- 주문/포지션
- 매수 판단 기준
- 자동으로 매수를 막는 조건
- 알림/동기화

Use bottom sheets on small screens and centered dialogs on desktop when practical.

Saved secrets are never echoed back. Display only `설정됨` / masked state, except the local-PC-only phone connection code described above.

## 12. Korean copy and beginner comprehension

The default dashboard must be understandable to a non-trader older adult without a glossary. A reasonable review standard is: **a Korean user in their 60s who has never heard the terms Regime, Entry, Context, risk-off, drawdown, profit factor, spread, slippage, or bps should still understand what the screen is telling them to do.**

Every primary state must answer three questions in ordinary Korean:

1. 지금 사는 쪽인가, 기다리는 쪽인가?
2. 왜 그렇게 판단했나?
3. 숫자가 높고 낮은 것이 무슨 뜻인가?

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

Technical terminology may remain under `자세히 보기`, settings marked as advanced, logs, or developer-facing files. The top-level dashboard and Telegram alerts must use ordinary Korean first.

Prefer:

- `지금은 새로 사지 않는 편이 낫습니다.`
- `시장 분위기는 좋지만 지금 가격은 조금 비싸 보입니다.`
- `전체 시장 분위기: 좋지 않음 (50/100)`
- `지금 매수 타이밍: 좋지 않음 (52/100)`

Avoid:

- bare `RISK_OFF`, `Regime 49.62`, `Entry 52.23`, `Context 48.2`
- long explanatory AI prose inside cards
- excessive `~할 수 있습니다`
- translated nouns such as `실행 가능성`, `전략적 함의` when a concrete verb works
- inconsistent `유저/사용자`, `설정/구성`, `체결/거래` terminology

## 13. Regression rules

- Do not change unrelated mobile geometry while fixing desktop.
- Do not introduce a second owner for the same selected/scroll state.
- Do not make live polling trigger layout shifts.
- Do not hide system errors merely to keep the dashboard visually clean.
- Do not make a graph look complete when there is insufficient history; show the data-collection state.
- Do not expose secrets to Git, Drive, Telegram, browser URL, or chart payloads.
