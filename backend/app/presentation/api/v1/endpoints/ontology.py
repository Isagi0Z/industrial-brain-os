from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.infrastructure.di.container import container

router = APIRouter(prefix="/ontology", tags=["Ontology"])
logger = logging.getLogger(__name__)
_bearer = HTTPBearer()


async def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Dict[str, Any]:
    token_service = container.get_token_service()
    payload = token_service.verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload


# ------------------------------------------------------------------
# Response schemas
# ------------------------------------------------------------------


class NodeTypeOut(BaseModel):
    required_properties: List[str]
    optional_properties: List[str]


class RelationOut(BaseModel):
    source: str
    relation: str
    target: str


class OntologySchemaOut(BaseModel):
    version: str
    node_types: Dict[str, NodeTypeOut]
    allowed_relations: List[RelationOut]


# ------------------------------------------------------------------
# Endpoint
# ------------------------------------------------------------------


@router.get(
    "/schema",
    response_model=OntologySchemaOut,
    summary="Return the Industrial Ontology schema",
)
def get_ontology_schema(
    _user: Dict[str, Any] = Depends(_get_current_user),
) -> OntologySchemaOut:
    validator = container.get_ontology_validator()
    schema = validator.get_schema()

    return OntologySchemaOut(
        version=schema.version,
        node_types={
            name: NodeTypeOut(
                required_properties=spec.required_properties,
                optional_properties=spec.optional_properties,
            )
            for name, spec in schema.node_types.items()
        },
        allowed_relations=[
            RelationOut(
                source=r.source_type,
                relation=r.relation_type,
                target=r.target_type,
            )
            for r in schema.allowed_relations
        ],
    )
