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

    # Deduplicate nodes by tag; the first type seen for a tag wins. The seed
    # tag is always present as a node even when it has no edges.
    node_types: Dict[str, str] = {entity_tag: "Unknown"}
    for p in paths:
        if p.source_tag:
            node_types.setdefault(p.source_tag, p.source_type or "Unknown")
            if p.source_type:
                node_types[p.source_tag] = p.source_type
        if p.target_tag:
            node_types.setdefault(p.target_tag, p.target_type or "Unknown")
            if p.target_type:
                node_types[p.target_tag] = p.target_type

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
