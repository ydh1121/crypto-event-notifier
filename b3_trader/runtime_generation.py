from __future__ import annotations

# Runtime generation marker used by the supervised Git auto-sync path.
# Changing this file intentionally causes the launcher to perform its normal
# exit-code-75 restart so newly added long-lived collectors are loaded without
# any manual process termination.
RUNTIME_GENERATION = "full-cost-ladder-v1"
