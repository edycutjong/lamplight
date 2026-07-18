"""lamplight-memory — a domain-agnostic shift-handover memory engine.

Episodic store + decay classes + nightly consolidation + contradiction
flags + token-budget briefs with mechanical citation validation + a signed,
hash-chained op ledger. Built for clinical handover (Lamplight), reusable
for any shift-based operation (see examples/support_handover.py).
"""

from .brief import DEFAULT_BUDGET, MAX_CARDS, BriefBuilder, handover_query
from .chain import ChainAudit, ChainReport, OpChain, demo_signing_key
from .consolidate import Consolidator
from .contradiction import ContradictionResolver
from .decay import DecayPolicy
from .engine import LamplightEngine
from .packer import BudgetPacker, BudgetViolation, PackCandidate, PackResult
from .schemas import (
    Brief,
    BriefCard,
    DecayClass,
    Episode,
    EpisodeType,
    MemoryItem,
    OpType,
    Status,
)
from .sealed import Sealer
from .store import Candidate, MemoryStore, cosine
from .tokens import approx_tokens
from .transport import FakeQwen, Transport, get_transport
from .validator import CitationValidator, ValidationResult

__version__ = "1.1.0"

__all__ = [
    "__version__",
    "LamplightEngine",
    "MemoryStore",
    "Candidate",
    "cosine",
    "DecayPolicy",
    "Consolidator",
    "ContradictionResolver",
    "BudgetPacker",
    "BudgetViolation",
    "PackCandidate",
    "PackResult",
    "BriefBuilder",
    "handover_query",
    "DEFAULT_BUDGET",
    "MAX_CARDS",
    "CitationValidator",
    "ValidationResult",
    "OpChain",
    "ChainAudit",
    "ChainReport",
    "demo_signing_key",
    "Sealer",
    "approx_tokens",
    "Transport",
    "FakeQwen",
    "get_transport",
    "Episode",
    "EpisodeType",
    "MemoryItem",
    "Brief",
    "BriefCard",
    "DecayClass",
    "Status",
    "OpType",
]
