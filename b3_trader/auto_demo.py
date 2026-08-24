from __future__ import annotations

# Compatibility facade. Existing imports/tests keep using b3_trader.auto_demo while
# the active implementation lives in auto_demo_v2.
from .auto_demo_v2 import *  # noqa: F401,F403
from .auto_demo_v2 import main


if __name__ == "__main__":
    main()
