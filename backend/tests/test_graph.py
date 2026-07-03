"""M19 Knowledge Graph subgraph endpoint tests.

Verifies the KGPath -> Cytoscape transformation: node de-duplication, seed
flagging, ontology type propagation, and the elements shape the frontend
``KnowledgeGraphView`` consumes. The traversal service is faked so the test is
pure (no Neo4j).
"""

from __future__ import annotations

import asyncio

from app.domain.graphrag.models import KGPath
from app.presentation.api.v1.endpoints import graph as graph_ep


class _FakeTraversal:
    def __init__(self, paths):
        self._paths = paths
        self.calls = []

    def traverse(self, tags, max_depth, limit):
        self.calls.append((tags, max_depth, limit))
        return self._paths


def _run(entity_tag, paths, depth=1, monkeypatch_container=None):
    fake = _FakeTraversal(paths)
    orig = graph_ep.container.get_kg_traversal_service
    graph_ep.container.get_kg_traversal_service = lambda: fake  # type: ignore[assignment]
    try:
        result = asyncio.run(
            graph_ep.get_subgraph(
                entity_tag=entity_tag,
                depth=depth,
                limit=200,
                current_user=object(),  # auth is dependency-injected; unused here
            )
        )
    finally:
        graph_ep.container.get_kg_traversal_service = orig  # type: ignore[assignment]
    return result, fake


def test_subgraph_builds_cytoscape_elements():
    paths = [
        KGPath("P-102A", "Equipment", "MONITORS", "FT-101", "Sensor"),
        KGPath("P-102A", "Equipment", "EXHIBITS", "FM-BRG-01", "FailureMode"),
    ]
    result, fake = _run("P-102A", paths, depth=2)

    assert result["seed"] == "P-102A"
    assert result["depth"] == 2
    assert fake.calls == [(["P-102A"], 2, 200)]

    node_ids = {n["data"]["id"] for n in result["nodes"]}
    assert node_ids == {"P-102A", "FT-101", "FM-BRG-01"}
    node_types = {n["data"]["id"]: n["data"]["type"] for n in result["nodes"]}
    assert node_types["FT-101"] == "Sensor"
    assert node_types["FM-BRG-01"] == "FailureMode"

    seed_nodes = [n for n in result["nodes"] if n["data"]["seed"]]
    assert [n["data"]["id"] for n in seed_nodes] == ["P-102A"]

    assert result["stats"] == {"node_count": 3, "edge_count": 2}
    edge_labels = {e["data"]["label"] for e in result["edges"]}
    assert edge_labels == {"MONITORS", "EXHIBITS"}


def test_seed_node_present_when_no_edges():
    result, _ = _run("VLV-501", [])
    assert result["nodes"] == [
        {"data": {"id": "VLV-501", "label": "VLV-501", "type": "Unknown", "seed": True}}
    ]
    assert result["edges"] == []
    assert result["stats"] == {"node_count": 1, "edge_count": 0}


def test_nodes_deduplicated_across_paths():
    paths = [
        KGPath("P-102A", "Equipment", "MONITORS", "FT-101", "Sensor"),
        KGPath("FT-101", "Sensor", "IS_PART_OF", "P-102A", "Equipment"),
    ]
    result, _ = _run("P-102A", paths)
    assert result["stats"]["node_count"] == 2  # P-102A and FT-101, not 4
    assert result["stats"]["edge_count"] == 2
