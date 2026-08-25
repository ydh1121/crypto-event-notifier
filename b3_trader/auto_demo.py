from __future__ import annotations

# Compatibility facade. Existing imports/tests keep using b3_trader.auto_demo.
# Constants/helpers continue to come from v3, while the active Bithumb runtime
# now uses the guarded Phase 3 exchange+market+strategy scoped store.
from .auto_demo_v3 import *  # noqa: F401,F403
from .bithumb_scoped_demo import BithumbScopedPaperDemo, main

AutoPaperDemo = BithumbScopedPaperDemo


if __name__ == "__main__":
    main()
