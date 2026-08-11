"""PRC-001 skills/adapters: collect, extract, validate, compare, alert.
Each module exposes a `make_*_handler()` factory producing a
`core.executor.TaskHandler`-compatible closure, since the underlying
`BaseAdapter`/`BaseSkill` protocol method names (`fetch`/`run`) differ
from that calling convention.
"""
