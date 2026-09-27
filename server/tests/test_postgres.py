import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from server.api import create_app
from server.models import TikTokConnection

TOKEN = "ci-only-operator-token-longer-than-32-characters"


@pytest.mark.skipif(not os.environ.get("DATABASE_URL", "").startswith("postgresql+psycopg://"), reason="PostgreSQL URL not configured")
def test_live_postgres_constraints_restart_and_decimal():
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url)
    assert "commerce_events" in inspect(engine).get_table_names()
    current = datetime.now(timezone.utc)
    with Session(engine) as session:
        record = session.get(TikTokConnection, "ci-account")
        if record is None:
            session.add(TikTokConnection(connection_id="ci-account",operator_id="primary",
                provider_user_id="CI-FAKE-NO-REAL-ACCOUNT",granted_scopes="user.info.basic",status="ACTIVE",
                connected_at=current,last_validated_at=current,access_expires_at=current+timedelta(days=1),
                refresh_expires_at=current+timedelta(days=365),manual_verified_at=current,
                manual_uk_evidence_ref="ci:market:uk",manual_affiliate_evidence_ref="ci:affiliate:status"))
            session.commit()
    suffix = uuid4().hex[:12]
    eid = f"EXP-PG-{suffix}"
    payload = {"experiment_id": eid, "decision_id": f"DEC-{suffix}", "product_id": "p1", "creative_id": "c1",
               "publication_action_id": f"publish-{eid}", "authority_evidence_ref": "ci:manual:authority"}
    c = TestClient(create_app(url, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    assert c.post("/v1/experiments", json=payload).status_code == 200
    timestamp = datetime.now(timezone.utc).isoformat()

    def post_event(kind, ext, amount=None):
        return c.post("/v1/events", json={"experiment_id": eid, "action_id": f"publish-{eid}",
             "source": "MANUAL_VERIFIED", "external_event_id": f"{suffix}-{ext}", "event_type": kind,
             "amount_gbp": amount, "evidence_ref": f"ci:evidence:{ext}", "occurred_at": timestamp})

    assert post_event("PUBLISHED", "video").status_code == 200
    assert post_event("ORDER_CREATED", "order").status_code == 200
    assert post_event("DELIVERED", "delivery").status_code == 200
    assert post_event("COMMISSION_SETTLED", "settlement", "1.99").status_code == 200
    assert c.post("/v1/costs", json={"experiment_id": eid, "amount_gbp": "0.99", "evidence_ref": "ci:observed:cost"}).status_code == 200
    assert c.get(f"/v1/experiments/{eid}/economics").json()["realized_contribution_gbp"] == "1.00"
    recovered = TestClient(create_app(url, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    assert recovered.post("/v1/events", json={"experiment_id": eid, "action_id": f"publish-{eid}",
             "source": "MANUAL_VERIFIED", "external_event_id": f"{suffix}-settlement", "event_type": "COMMISSION_SETTLED",
             "amount_gbp": "1.99", "evidence_ref": "ci:evidence:settlement", "occurred_at": timestamp}).json()["duplicate"] is True
    assert post_event("REFUNDED", "refund", "0.01").status_code == 200
    assert recovered.get(f"/v1/experiments/{eid}/economics").json()["realized_contribution_gbp"] == "0.99"
