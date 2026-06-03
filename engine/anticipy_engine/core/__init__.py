"""The control core — the brain and the nervous system.

Built against stub workers so the hardest part of the product (deciding,
planning, running, verifying) is proven end to end before any real hand, memory,
or channel exists. The bus + the frozen worker contract are the scalability
design: real workers swap in for stubs with zero orchestrator change.
"""
