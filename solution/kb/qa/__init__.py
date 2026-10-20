"""Question answering: one Claude call per question over the top search results."""
from .answerer import Answerer, make_client

__all__ = ["Answerer", "make_client"]
