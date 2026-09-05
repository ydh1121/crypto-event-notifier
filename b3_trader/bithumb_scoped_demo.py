from __future__ import annotations

from .auto_demo_v2 import DETAIL_DIR, STATUS_PATH
from .multi_exchange_paper import MultiExchangePaperDemo


class BithumbScopedPaperDemo(MultiExchangePaperDemo):
    """Bithumb PAPER runtime backed by exchange+market+strategy scoped storage.

    The legacy SQLite tables remain untouched for rollback/audit. On the first
    scoped start, their latest state/history is copied and verified before the
    cutover marker is written. Subsequent starts never re-import stale legacy
    state. Output paths stay backward-compatible with the existing dashboard and
    Cloudflare publishers.
    """

    def __init__(self) -> None:
        super().__init__("bithumb", "adaptive")
        try:
            self.cutover = self.store.cutover_legacy_bithumb()
        except Exception:
            self.store.close()
            raise
        self.status_path = STATUS_PATH
        self.detail_dir = DETAIL_DIR


# Compatibility name used by b3_trader.auto_demo and local_app.
AutoPaperDemo = BithumbScopedPaperDemo


def main() -> None:
    BithumbScopedPaperDemo().run()


if __name__ == "__main__":
    main()
