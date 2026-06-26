from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "Industrial Brain OS API"


def test_health_check_stub():
    # Since DBs might be running but some credentials might change,
    # we call the health endpoint and check the structure of the JSON response.
    response = client.get("/api/v1/health")
    # Health endpoint can return either 200 (healthy) or 503 (if any DB connectivity fails)
    assert response.status_code in [200, 503]

    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "databases" in data
    assert "postgres" in data["databases"]
    assert "neo4j" in data["databases"]
    assert "qdrant" in data["databases"]
    assert "redis" in data["databases"]
    assert "minio" in data["databases"]
