"""Feedback package — result reporting and progressive hints.

Two rules govern everything here:

1. **Facts come from the checker, explanation comes from the AI.** A hint never
   contradicts or replaces a deterministic test result.
2. **Hidden data stays hidden.** Hidden test inputs and expected outputs are
   never sent to a client or included in an AI prompt.
"""

from app.feedback.hint_service import HintService, HintUnavailableError
from app.feedback.reporter import ResultReporter, summarize_failures

__all__ = [
    "HintService",
    "HintUnavailableError",
    "ResultReporter",
    "summarize_failures",
]
