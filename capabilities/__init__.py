"""Capabilities: the plug-ins an Observer can be taught, one package each.

Nothing here is imported by ``observer/``. The dependency runs one way — a
capability knows the chassis, the chassis never knows a capability — which is
what allows a new one to be written without touching the motherboard.
"""

from .anomaly import AnomalyListener

__all__ = ["AnomalyListener"]
