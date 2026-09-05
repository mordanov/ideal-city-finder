import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Patch settings before the app module is imported so that the auth service
# sees the test credentials rather than whatever is (or isn't) in .env.
# ---------------------------------------------------------------------------
TEST_USER1 = ("alice", "secret1")
TEST_USER2 = ("bob", "secret2")
TEST_JWT_SECRET = "test-secret-key"


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    import app.config as cfg

    monkeypatch.setattr(cfg.settings, "auth_user_1_username", TEST_USER1[0])
    monkeypatch.setattr(cfg.settings, "auth_user_1_password", TEST_USER1[1])
    monkeypatch.setattr(cfg.settings, "auth_user_2_username", TEST_USER2[0])
    monkeypatch.setattr(cfg.settings, "auth_user_2_password", TEST_USER2[1])
    monkeypatch.setattr(cfg.settings, "jwt_secret_key", TEST_JWT_SECRET)
    monkeypatch.setattr(cfg.settings, "jwt_expire_minutes", 60)


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Login endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_user1(client):
    resp = await client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert resp.cookies.get("access_token") is not None


@pytest.mark.asyncio
async def test_login_user2(client):
    resp = await client.post("/api/auth/login", json={"username": "bob", "password": "secret2"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_wrong_password(client):
    resp = await client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_username(client):
    resp = await client.post("/api/auth/login", json={"username": "nobody", "password": "secret1"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected endpoint (GET /api/search/) with malformed JWT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_jwt_rejected(client):
    resp = await client.get("/api/search/", headers={"Authorization": "Bearer this.is.garbage"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_auth_rejected(client):
    resp = await client.get("/api/search/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_accepted(client):
    # Log in first to get a real token
    login = await client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    token = login.json()["access_token"]

    resp = await client.get("/api/search/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
