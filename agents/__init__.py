"""Agents: processes that reason over AIOP, above the layers that hold it.

An agent here is temporary by design. It reads objects out of the store,
reasons, and writes objects back; it keeps no private knowledge, so nothing is
lost when it stops and nothing has to be re-explained when the next one starts.
The knowledge belongs to AIOP.
"""

__all__ = []
