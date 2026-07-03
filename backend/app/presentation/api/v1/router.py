from fastapi import APIRouter
from app.presentation.api.v1.endpoints import (
    health,
    auth,
    document,
    search,
    chat,
    ontology,
    graph,
    knowledge_brain,
    maintenance_brain,
    compliance_brain,
    rca_brain,
    incidents,
    lessons_brain,
    jobs,
    eval as eval_endpoint,
)

api_router = APIRouter()

# Include health router at the top
api_router.include_router(health.router, tags=["System Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(document.router)
api_router.include_router(search.router)
api_router.include_router(chat.router)
api_router.include_router(ontology.router)
api_router.include_router(graph.router)
api_router.include_router(knowledge_brain.router)
api_router.include_router(maintenance_brain.router)
api_router.include_router(compliance_brain.router)
api_router.include_router(rca_brain.router)
api_router.include_router(incidents.router)
api_router.include_router(lessons_brain.router)
api_router.include_router(jobs.router)
api_router.include_router(eval_endpoint.router)


# Placeholder routers for the five core sub-brains
@api_router.get("/knowledge/status", tags=["Knowledge Brain"])
def get_knowledge_status():
    return {"sub_brain": "Knowledge", "status": "active", "scaffold": True}


@api_router.get("/maintenance/status", tags=["Maintenance Brain"])
def get_maintenance_status():
    return {"sub_brain": "Maintenance", "status": "active", "scaffold": True}


@api_router.get("/compliance/status", tags=["Compliance Brain"])
def get_compliance_status():
    return {"sub_brain": "Compliance", "status": "active", "scaffold": True}


@api_router.get("/rca/status", tags=["RCA Brain"])
def get_rca_status():
    return {"sub_brain": "RCA", "status": "active", "scaffold": True}


@api_router.get("/lessons-learned/status", tags=["Lessons Learned Brain"])
def get_lessons_status():
    return {"sub_brain": "Lessons Learned", "status": "active", "scaffold": True}
