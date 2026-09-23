"""Process identities shared by the normal launcher and read-only review."""

# Preserve the existing launcher order and arguments. The holdings consumer is
# started by that launcher as before, but gains no new automatic retry policy.
SIDECARS = (
    ("forward", "b3_trader.forward_pipeline_scheduler", (), True),
    ("market_flow", "b3_trader.market_flow_stream", (), True),
    ("research", "b3_trader.research_supervisor", (), True),
    ("paper", "b3_trader.paper_runtime_supervisor", (), True),
    ("holdings", "b3_trader.holding_mutation_consumer", ("--interval", "5"), False),
)
APP_MODULE = "b3_trader.local_app"
HOST_STATUS = "b3_trader/data/local-process-host.json"
HOST_LOCK = "b3_trader/data/local-process-host.lock"
HOST_LOGS = "b3_trader/data/local-process-logs"
