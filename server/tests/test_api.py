from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from server.api import create_app
from server.models import Base


TOKEN = "test-only-operator-secret-32-characters-long"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def database(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ledger.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield url


def client(url):
    return TestClient(create_app(url, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})


def experiment(experiment_id="EXP-001"):
    return {"experiment_id": experiment_id, "decision_id": "DEC-001", "product_id": "product-1",
            "creative_id": "creative-1", "publication_action_id": f"publish-{experiment_id}",
            "authority_evidence_ref": "operator:approved:1", "market": "UK", "currency": "GBP"}


def event(event_type, external_event_id, amount=None, experiment_id="EXP-001"):
    return {"experiment_id": experiment_id, "action_id": f"publish-{experiment_id}",
            "source": "MANUAL_VERIFIED", "external_event_id": external_event_id,
            "event_type": event_type, "amount_gbp": amount, "evidence_ref": f"receipt:{external_event_id}",
            "occurred_at": "2026-09-27T10:00:00Z"}


def test_migration_round_trip_and_metadata(database):
    engine = create_engine(database)
    assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())
    cfg = Config(str(ROOT / "alembic.ini"))
    command.downgrade(cfg, "base")
    assert "experiments" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "commerce_events" in inspect(engine).get_table_names()


def test_auth_and_missing_publication_fail_closed(database):
    anonymous = TestClient(create_app(database, TOKEN))
    assert anonymous.post("/v1/experiments", json=experiment()).status_code == 401
    c = client(database)
    assert c.post("/v1/experiments", json=experiment()).status_code == 200
    assert c.post("/v1/events", json=event("COMMISSION_SETTLED", "s1", "2.00")).status_code == 409
    assert c.post("/v1/events", json=event("PUBLISHED", "video-1", "2.00")).status_code == 422
    assert c.post("/v1/events", json=event("PUBLISHED", "video-1")).status_code == 200
    assert c.post("/v1/events", json=event("PUBLISHED", "video-2")).status_code == 409
    assert c.post("/v1/events", json=event("REFUNDED", "refund-1")).status_code == 422


def test_restart_exact_retry_conflict_and_refund_revocation(database):
    c = client(database)
    assert c.post("/v1/experiments", json=experiment()).json()["duplicate"] is False
    assert c.post("/v1/experiments", json=experiment()).json()["duplicate"] is True
    assert c.post("/v1/experiments", json={**experiment(), "decision_id": "DEC-OTHER"}).status_code == 409
    for typ, ext, amount in [("PUBLISHED", "video", None), ("ORDER_CREATED", "order", None),
                             ("DELIVERED", "delivered", None), ("COMMISSION_SETTLED", "settlement", "2.00")]:
        assert c.post("/v1/events", json=event(typ, ext, amount)).status_code == 200
    assert c.post("/v1/costs", json={"experiment_id": "EXP-001", "amount_gbp": "0.01", "evidence_ref": "receipt:cost"}).status_code == 200
    before = c.get("/v1/experiments/EXP-001/economics").json()
    assert before["realized_contribution_gbp"] == "1.99"
    assert before["local_first_pound_candidate"] is True
    assert before["commercial_proof"] == "NOT_PROVEN"
    recovered = client(database)
    assert recovered.post("/v1/events", json=event("COMMISSION_SETTLED", "settlement", "2.00")).json()["duplicate"] is True
    assert recovered.post("/v1/events", json=event("COMMISSION_SETTLED", "settlement", "9.00")).status_code == 409
    assert recovered.post("/v1/events", json=event("REFUNDED", "refund", "1.01")).status_code == 200
    after = recovered.get("/v1/experiments/EXP-001/economics").json()
    assert after["net_settled_gbp"] == "0.99"
    assert after["realized_contribution_gbp"] == "0.98"
    assert after["local_first_pound_candidate"] is False
    assert after["commercial_proof"] == "NOT_PROVEN"


def test_money_and_cross_experiment_guards(database):
    c = client(database)
    assert c.post("/v1/experiments", json=experiment()).status_code == 200
    assert c.post("/v1/events", json=event("PUBLISHED", "video")).status_code == 200
    assert c.post("/v1/events", json=event("COMMISSION_SETTLED", "fractional", "1.001")).status_code == 422
    assert c.post("/v1/events", json=event("COMMISSION_SETTLED", "negative", "-1.00")).status_code == 422
    assert c.post("/v1/events", json=event("COMMISSION_SETTLED", "cross", "99.00", "EXP-002")).status_code == 409
    assert c.get("/v1/experiments/EXP-001/economics").json()["net_settled_gbp"] is None


def test_configuration_requires_server_side_secret(database):
    with pytest.raises(RuntimeError):
        create_app(database, "short")
