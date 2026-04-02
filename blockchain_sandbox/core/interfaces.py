from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, TypeVar

from .entities import Block, Node
from .graph_model import DirectedGraph

TEvent = TypeVar("TEvent")


class IEventBus(ABC):
    """
    Central event bus for decoupling simulation components.
    """
    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> None:
        pass

    @abstractmethod
    def publish(self, event_type: str, payload: Any) -> None:
        pass


class ISimulationContext(ABC):
    """
    Provides access to the shared simulation state for modules.
    """
    @property
    @abstractmethod
    def current_time(self) -> float:
        pass

    @property
    @abstractmethod
    def current_step(self) -> int:
        pass

    @property
    @abstractmethod
    def nodes(self) -> Dict[str, Node]:
        pass

    @property
    @abstractmethod
    def blocks(self) -> Dict[str, Block]:
        pass

    @property
    @abstractmethod
    def graph(self) -> DirectedGraph:
        pass

    @property
    @abstractmethod
    def chain_heights(self) -> Dict[str, int]:
        pass
        
    @property
    @abstractmethod
    def private_chains(self) -> Dict[str, List[str]]:
        pass
        
    @abstractmethod
    def get_canonical_head(self) -> str:
        pass

    @abstractmethod
    def schedule_event(self, delay: float, kind: str, a: str, b: str, hops: int = 0) -> None:
        pass


class ISimulationModule(ABC):
    """
    Base interface for all pluggable modules.
    """
    @abstractmethod
    def setup(self, ctx: ISimulationContext, bus: IEventBus) -> None:
        """Called once during simulation initialization."""
        pass

    def on_step_start(self, ctx: ISimulationContext) -> None:
        """Called at the beginning of a discrete event step."""
        pass

    def augment_agent_observation(self, miner_id: str, ctx: ISimulationContext) -> Dict[str, Any]:
        """Provide additional context for the LLM agent's observation."""
        return {}
        
    def augment_system_prompt(self, miner_id: str, ctx: ISimulationContext) -> str:
        """Provide additional instructions for the LLM agent's system prompt."""
        return ""
        
    def expected_decision_keys(self) -> Dict[str, str]:
        """Define expected keys and their types (e.g., int, str) for LLM JSON output."""
        return {}


class EventTypes:
    # Core events
    SIMULATION_START = "simulation_start"
    SIMULATION_END = "simulation_end"
    
    # Block events
    BLOCK_MINED = "block_mined"          # payload: {'miner_id': str, 'block': Block}
    BLOCK_RECEIVED = "block_received"    # payload: {'node_id': str, 'block_id': str, 'hops': int, 'changed_head': bool}
    
    # LLM & Decision events
    AGENT_DECISION_MADE = "agent_decision_made" # payload: {'miner_id': str, 'decision': LLMDecision, 'effective': LLMDecision}
    
    # Strategy events
    PRIVATE_CHAIN_PUBLISHED = "private_chain_published" # payload: {'miner_id': str, 'blocks': List[str]}
    
    # Governance events
    NODE_BANNED = "node_banned"          # payload: {'node_id': str, 'reason': str, 'step': int}
