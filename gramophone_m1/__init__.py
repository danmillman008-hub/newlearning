"""Gramophone M1: local-first textbook-chapter -> knowledge graph + knowledge space.

Pipeline: PDF/Markdown -> text blocks -> entity-relation KG -> atomic knowledge
items -> prerequisite (surmise) DAG -> enumerated knowledge states + fringes.

Local-first: no servers, no vector DB, no cloud. No API keys required:
MockLLM (deterministic cassettes) is the default backend; GeminiFlashLLM is an
optional drop-in backend activated by GEMINI_API_KEY with zero architecture change.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
