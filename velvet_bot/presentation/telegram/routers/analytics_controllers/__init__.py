from __future__ import annotations

from .channel_message_runtime import install as install_channel_message_runtime
from .review_query_runtime import install as install_review_query_runtime

install_channel_message_runtime()
install_review_query_runtime()

__all__ = ()
