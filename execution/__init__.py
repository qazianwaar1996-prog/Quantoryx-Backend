# execution/__init__.py
"""
Quantoryx — Trade Execution Engine Package.

Exposes the centralized execution engine controller to manage trade order lifecycles [1].
"""

from execution.executor import ExecutionEngine

__all__ = [
    "ExecutionEngine",
]
