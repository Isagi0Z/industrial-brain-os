"""Knowledge Graph API endpoints (M19).

Exposes a bounded subgraph around an entity tag as Cytoscape-compatible JSON so
the frontend ``KnowledgeGraphView`` can render it as an interactive node-edge
diagram. Reuses the M8/M17 ``Neo4jKGTraversalService`` (APOC bounded traversal,
Engineering Bible §36 — no unconstrained full-graph scans); this endpoint adds
no new Cypher.
"""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, Query

from app.domain.auth.models import User
from app.domain.graphrag.models import KGPath
from app.infrastructure.di.container import container
from app.presentation.api.dependencies.auth import get_current_user

router = APIRouter(prefix="/graph", tags=["Knowledge Graph"])

# Bounds mirror the GraphRAG traversal guard — a demo visualization must never
# trigger an unbounded subgraph pull.
_MAX_DEPTH = 3
_MAX_EDGES = 200


def _node(tag: str, node_type: str, is_seed: bool) -> dict:
    """A Cytoscape node element. ``type`` drives the frontend colour scheme
    (Asset=blue, Equipment=green, Sensor=yellow, FailureMode=red, ...)."""
    return {
        "data": {
            "id": tag,
            "label": tag,
            "type": node_type or "Unknown",
            "seed": is_seed,
        }
    }


def _edge(path: KGPath) -> dict:
    return {
        "data": {
            "id": f"{path.source_tag}|{path.relation_type}|{path.target_tag}",
            "source": path.source_tag,
            "target": path.target_tag,
            "label": path.relation_type,
        }
    }


def _collect_node_types(paths: List[KGPath], seed_tag: str) -> Dict[str, str]:
    """Map each tag appearing in the paths to its ontology type. The seed tag is
    always present; a non-empty type from any path wins over ``Unknown``."""
    node_types: Dict[str, str] = {seed_tag: "Unknown"}
    for p in paths:
        for tag, ntype in (
            (p.source_tag, p.source_type),
            (p.target_tag, p.target_type),
        ):
            if not tag:
                continue
            if tag not in node_types or ntype:
                node_types[tag] = ntype or node_types.get(tag, "Unknown")
    return node_types


@router.get("/subgraph")
async def get_subgraph(
    entity_tag: str = Query(..., min_length=1, description="Seed entity tag number"),
    depth: int = Query(1, ge=1, le=_MAX_DEPTH, description="Traversal depth"),
    limit: int = Query(
        _MAX_EDGES, ge=1, le=_MAX_EDGES, description="Max edges to return"
    ),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the bounded subgraph around ``entity_tag`` as Cytoscape elements.

    Response: ``{seed, depth, nodes: [...], edges: [...], stats}`` where each
    node carries its ontology ``type`` for colour-coding and the seed node is
    flagged ``seed: true``.
    """
    traversal = container.get_kg_traversal_service()
    paths: List[KGPath] = traversal.traverse([entity_tag], depth, limit)

    # Deduplicate nodes by tag (seed always present, even with no edges).
    node_types = _collect_node_types(paths, entity_tag)

    nodes = [
        _node(tag, ntype, is_seed=(tag == entity_tag))
        for tag, ntype in node_types.items()
    ]
    edges = [_edge(p) for p in paths if p.source_tag and p.target_tag]

    return {
        "seed": entity_tag,
        "depth": depth,
        "nodes": nodes,
        "edges": edges,
        "stats": {"node_count": len(nodes), "edge_count": len(edges)},
    }
