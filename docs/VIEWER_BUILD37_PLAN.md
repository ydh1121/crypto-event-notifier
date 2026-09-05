# Viewer Build 37

Build 37 closes three QA gaps found after Build 36.

1. Coin-profile integrity is audited by content, not only by cached project name.
   - Exchange official Korean/English names stay authoritative.
   - Business-summary lead identity, provider id, homepage and evidence URLs are checked for foreign-project signals.
   - A mismatched profile is hidden in the Viewer and placed in the precision repair backlog.
   - The full integrity audit covers both Bithumb and Upbit caches.

2. Korean IME search composition is preserved.
   - Search inputs do not forward intermediate composition input to page rerender handlers.
   - The final composed Hangul string is dispatched once at compositionend.
   - This applies to sector, strategy, PAPER and other type=search inputs.

3. Comparison tables receive bidirectional sorting without changing layout width.
   - Sector coin metrics retain their existing bidirectional sort.
   - PAPER exchange comparison can sort its visible comparison columns.
   - Strategy overview, coin performance and coin×strategy tables can sort relevant numeric/text columns.
   - Live feeds, intentional rankings and master/detail lists keep their semantic fixed order.

Mobile layout rule: sorting must not add columns or new table min-width. Sector rows remain mobile cards at <=760px.
