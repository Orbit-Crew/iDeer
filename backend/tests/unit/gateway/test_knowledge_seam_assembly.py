"""#169: the production gateway seam wires the real device broker.

The graph, wiki and ask integration tests override ``knowledge_facade``
with a FakeBroker, so none of them could catch the production factory
omitting ``graph_broker_factory`` — every locally imported revision failed
with ``GRAPH_DEVICE_UNAVAILABLE`` before a single dispatch. This module
pins the production assembly itself: the same ``DeviceBroker`` the device
socket registers with must back the graph generator, the wiki writer, and
the graph answerer.
"""

import inspect

import pytest

from app.agentplatform.knowledge.facade import KnowledgeFacade
from app.device_control.broker import get_device_broker
from app.gateway.knowledge_seam import knowledge_facade
from deerflow.persistence import engine as persistence_engine


@pytest.fixture
def _persistence_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-None session factory, so ``persistence_factory`` passes; the
    facade constructor never opens a session."""
    monkeypatch.setattr(persistence_engine, "_session_factory", object(), raising=True)


def test_production_knowledge_facade_hands_over_the_real_device_broker(_persistence_ready) -> None:
    facade = knowledge_facade()
    # Identity, not a wrapper: the factory the seam hands over is exactly the
    # accessor the device websocket registers connections with.
    assert facade._graph_broker_factory is get_device_broker


def test_facade_shares_one_broker_factory_across_graph_wiki_and_ask(_persistence_ready) -> None:
    """The three consumers read one stored factory, so device availability is
    a single gateway fact rather than a per-capability wiring choice."""
    knowledge_facade()
    for consumer in (KnowledgeFacade._graph_generations, KnowledgeFacade._wiki_generations, KnowledgeFacade._graph_queries):
        assert "broker_factory=self._graph_broker_factory" in inspect.getsource(consumer)
