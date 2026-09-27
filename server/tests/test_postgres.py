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
    c = TestClient(create_app(url, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    timestamp = datetime.now(timezone.utc).isoformat()
    assert c.post('/v1/capital-authority',json={'authority_id':f'capital-{suffix}',
        'available_capital_gbp':'10.00','capital_limit_gbp':'8.00','loss_limit_gbp':'5.00',
        'minimum_allocation_score':60,'evidence_ref':f'ci:capital:{suffix}'}).status_code==200
    assert c.post('/v1/products',json={'product_id':f'product-{suffix}','listing_ref':f'ci:listing:{suffix}',
        'evidence_ref':f'ci:product:{suffix}','observed_at':timestamp}).status_code==200
    assert c.post('/v1/opportunities',json={'opportunity_id':f'opportunity-{suffix}',
        'product_id':f'product-{suffix}','capital_required_gbp':'3.00','maximum_loss_gbp':'2.00',
        'allocation_score':70,'evidence_ref':f'ci:opportunity:{suffix}','observed_at':timestamp}).status_code==200
    payload = {"experiment_id": eid, "decision_id": f"DEC-{suffix}", "product_id": "p1", "creative_id": "c1",
               "publication_action_id": f"publish-{eid}", "authority_evidence_ref": "ci:manual:authority",
               "opportunity_id":f'opportunity-{suffix}'}
    payload['product_id']=f'product-{suffix}'
    payload['creative_id']=f'creative-{suffix}'
    assert c.post("/v1/experiments", json=payload).status_code == 200
    assert c.post('/v1/product-claims',json={'claim_id':f'claim-{suffix}','product_id':payload['product_id'],
        'text':'Operator observed feature','state':'SUPPORTED','evidence_ref':f'ci:claim:{suffix}'}).status_code==200
    assert c.post('/v1/creatives',json={'creative_id':payload['creative_id'],'experiment_id':eid,
        'content':'Manual video concept','claim_ids':[f'claim-{suffix}'],
        'evidence_ref':f'ci:creative:{suffix}'}).status_code==200
    assert c.post('/v1/creative-approvals',json={'approval_id':f'approval-{suffix}',
        'experiment_id':eid,'creative_id':payload['creative_id'],
        'evidence_ref':f'ci:approval:{suffix}'}).status_code==200
    assert c.post('/v1/launch-intents',json={'packet_id':f'packet-{suffix}',
        'experiment_id':eid,'approval_id':f'approval-{suffix}'}).status_code==200

    def post_event(kind, ext, amount=None, parent=None):
        return c.post("/v1/events", json={"experiment_id": eid, "action_id": f"publish-{eid}",
             "source": "MANUAL_VERIFIED", "external_event_id": f"{suffix}-{ext}", "event_type": kind,
             "parent_external_event_id":f"{suffix}-{parent}" if parent else None,
             "amount_gbp": amount, "evidence_ref": f"ci:evidence:{ext}", "occurred_at": timestamp})

    assert post_event("PUBLISHED", "video").status_code == 200
    assert post_event("ORDER_CREATED", "order",parent='video').status_code == 200
    assert post_event("DELIVERED", "delivery",parent='order').status_code == 200
    assert post_event("COMMISSION_SETTLED", "settlement", "1.99",parent='order').status_code == 200
    assert c.post("/v1/costs", json={"experiment_id": eid, "amount_gbp": "0.99", "evidence_ref": "ci:observed:cost"}).status_code == 200
    assert c.get(f"/v1/experiments/{eid}/economics").json()["realized_contribution_gbp"] == "1.00"
    recovered = TestClient(create_app(url, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    assert recovered.post("/v1/events", json={"experiment_id": eid, "action_id": f"publish-{eid}",
             "source": "MANUAL_VERIFIED", "external_event_id": f"{suffix}-settlement", "event_type": "COMMISSION_SETTLED",
             "parent_external_event_id":f"{suffix}-order","amount_gbp": "1.99", "evidence_ref": "ci:evidence:settlement", "occurred_at": timestamp}).json()["duplicate"] is True
    assert post_event("REFUNDED", "refund", "0.01",parent='settlement').status_code == 200
    assert recovered.get(f"/v1/experiments/{eid}/economics").json()["realized_contribution_gbp"] == "0.99"
