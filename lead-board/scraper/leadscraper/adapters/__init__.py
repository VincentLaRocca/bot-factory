"""Available board adapters."""

from . import craigslist


ADAPTERS = {"craigslist": craigslist.parse}
