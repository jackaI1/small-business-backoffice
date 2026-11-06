"""Small, explicit IFRS-style consolidation workpapers, not statutory certification."""

from .model import CloseError, consolidate, roll_up_plan

__all__ = ["CloseError", "consolidate", "roll_up_plan"]
