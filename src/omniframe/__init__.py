"""OmniFrame — MCP server for vertical video production."""

from ._compat import mirror_legacy_env

__version__ = "3.0.0.dev0"

__all__ = ["__version__"]

# Old ARGUS_* variables become OMNIFRAME_* before any module reads them.
mirror_legacy_env()
