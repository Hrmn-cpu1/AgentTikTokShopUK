"""Engineering journey with a fake Login Kit provider; no real TikTok or money."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from server.api import create_app
from server.models import TikTokConnection
from server.tests.test_tiktok_connection import FakeProvider, LOGIN, TOKEN, ENCRYPTION_KEY


@pytest.fixture()
def system(tmp_path):
    url = f"sqlite:///{tmp_path / 'e2e.db'}"
    command.upgrade(_config(url), 'head')
    provider = FakeProvider()
    def client():
        return TestClient(create_app(url, TOKEN, tiktok_provider=provider,
            operator_login_secret=LOGIN, token_encryption_key=ENCRYPTION_KEY), base_url='https://agent.example')
    return url, provider, client


def _config(url):
    from os import environ
    environ['DATABASE_URL'] = url
    return Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))


def post(c, path, payload):
    return c.post('/v1/' + path, json=payload, headers={'X-CSRF-Token':c.cookies.get('operator_csrf', '')})


def authenticate(system):
    url, provider, new_client = system
    c = new_client()
    assert c.get('/v1/portfolio').status_code == 401
    assert c.post('/v1/operator/login', json={'access_key': LOGIN}).status_code == 200
    assert c.get('/v1/tiktok/connection').json()['capabilities']['AFFILIATE'] == 'UNKNOWN'
    result = post(c, 'tiktok/android-intent', {})
    assert result.status_code == 200
    state = result.json()['state']
    response = post(c, 'tiktok/android-exchange', {'state':state,'code':'valid-code','code_verifier':'v'*32})
    assert response.status_code == 200
    assert response.json()['connection']['status']=='ACTIVE'
    assert c.get('/v1/tiktok/connection').json()['capabilities']['IDENTITY']=='AVAILABLE'
    assert post(c, 'tiktok/manual-verification', {'uk_market_evidence_ref':'shop:verified:uk',
        'affiliate_evidence_ref':'affiliate:manual:receipt'}).json()['mode']=='MANUAL_VERIFIED'
    return c


def setup_authority(c, *, capital='8.00', loss='5.00', allocation='3.00', risk='2.00'):
    observed = datetime.now(timezone.utc).isoformat()
    assert post(c,'capital-authority',{'authority_id':'capital-1','available_capital_gbp':'10.00',
        'capital_limit_gbp':capital,'loss_limit_gbp':loss,'minimum_allocation_score':60,
        'evidence_ref':'operator:capital:1'}).status_code == 200
    assert post(c,'products',{'product_id':'product-1','listing_ref':'listing:uk:real:1',
        'evidence_ref':'operator:listing:1','observed_at':observed}).status_code == 200
    assert post(c,'opportunities',{'opportunity_id':'opportunity-1','product_id':'product-1',
        'capital_required_gbp':allocation,'maximum_loss_gbp':risk,'allocation_score':70,
        'evidence_ref':'operator:opportunity:1','observed_at':observed}).status_code == 200
    return {'experiment_id':'EXP-001','decision_id':'DEC-001','product_id':'product-1','creative_id':'creative-1',
        'publication_action_id':'ACTION-001','authority_evidence_ref':'operator:decision:1',
        'opportunity_id':'opportunity-1'}


def prepare_launch(c, experiment):
    assert post(c,'experiments',experiment).status_code == 200
    claim = {'claim_id':'claim-1','product_id':'product-1','text':'Demonstrated feature',
        'state':'SUPPORTED','evidence_ref':'operator:claim:1'}
    assert post(c,'product-claims',claim).status_code == 200
    creative = {'creative_id':'creative-1','experiment_id':'EXP-001','content':'Human-reviewed video draft',
        'claim_ids':['claim-1'],'evidence_ref':'operator:creative:1'}
    assert post(c,'creatives',creative).status_code == 200
    approval = {'approval_id':'approval-1','experiment_id':'EXP-001','creative_id':'creative-1',
        'evidence_ref':'operator:approval:1'}
    assert post(c,'creative-approvals',approval).status_code == 200
    packet = {'packet_id':'packet-1','experiment_id':'EXP-001','approval_id':'approval-1'}
    result = post(c,'launch-intents',packet)
    assert result.status_code == 200 and result.json()['externalExecutionAllowed'] is False
    return claim, creative, approval, packet


def event(c, kind, external, *, parent=None, amount=None):
    return post(c,'events',{'experiment_id':'EXP-001','action_id':'ACTION-001',
        'source':'MANUAL_VERIFIED','external_event_id':external,'parent_external_event_id':parent,
        'event_type':kind,'amount_gbp':amount,'evidence_ref':f'operator:receipt:{external}',
        'occurred_at':'2026-09-27T10:00:00Z'})


def test_complete_manual_engineering_journey_refund_restart_and_learning(system):
    c = authenticate(system)
    experiment = setup_authority(c)
    prepare_launch(c, experiment)
    assert event(c,'PUBLISHED','video-1').status_code == 200
    assert event(c,'ORDER_CREATED','order-1',parent='video-1').status_code == 200
    assert event(c,'COMMISSION_SETTLED','premature',parent='order-1',amount='5.00').status_code == 409
    assert event(c,'DELIVERED','delivered-1',parent='order-1').status_code == 200
    settlement = event(c,'COMMISSION_SETTLED','settlement-1',parent='order-1',amount='5.00')
    assert settlement.status_code == 200
    assert post(c,'costs',{'experiment_id':'EXP-001','amount_gbp':'3.00',
        'evidence_ref':'operator:cost:1'}).status_code == 200
    assert c.get('/v1/portfolio').json()['experiments'][0]['realizedContributionGbp']=='2.00'
    assert c.get('/v1/portfolio').json()['experiments'][0]['firstPoundCandidate'] is True
    result = post(c,'learning',{'learning_id':'learning-1','experiment_id':'EXP-001'})
    assert result.json()['contributionGbp']=='2.00' and result.json()['source']=='MANUAL_ASSERTION'
    assert event(c,'REFUNDED','refund-1',parent='settlement-1',amount='2.00').status_code == 200
    recovered = system[2]()
    recovered.cookies.update(c.cookies)
    assert recovered.get('/v1/portfolio').json()['experiments'][0]['realizedContributionGbp']=='0.00'
    assert recovered.get('/v1/portfolio').json()['experiments'][0]['firstPoundCandidate'] is False
    assert recovered.get('/v1/learning').json()['records'][0]['current'] is False
    assert post(recovered,'learning',{'learning_id':'learning-1','experiment_id':'EXP-001'}).status_code == 409
    assert post(recovered,'learning',{'learning_id':'learning-2','experiment_id':'EXP-001'}).json()['contributionGbp']=='0.00'
    assert recovered.get('/v1/portfolio').json()['commercialProof']=='NOT_PROVEN'
    assert recovered.get('/ready').json()['status']=='ready'


def test_private_apk_web_login_returns_connected_identity_without_browser_session(system):
    _, provider, new_client=system
    app=new_client()
    assert app.post('/v1/operator/login',json={'access_key':LOGIN}).status_code==200
    csrf=app.cookies.get('operator_csrf')
    start=app.post('/v1/tiktok/native-web-intent',headers={'X-CSRF-Token':csrf})
    assert start.status_code==200
    authorization=start.json()['authorizationUrl']
    assert authorization.startswith('https://www.tiktok.com/v2/auth/authorize/')
    assert 'scope=user.info.basic' in authorization
    state=parse_qs(urlparse(authorization).query)['state'][0]

    # The external system browser has no Capacitor WebView operator cookie.
    browser_callback=new_client()
    response=browser_callback.get('/v1/tiktok/callback',params={'state':state,'code':'valid-code'},
        follow_redirects=False)
    assert response.status_code==200
    assert response.headers['content-type'].startswith('text/html')
    assert 'Volte ao AgentTikTok Shop' in response.text
    assert browser_callback.get('/v1/tiktok/callback',params={'state':state,'code':'valid-code'},
        follow_redirects=False).status_code==403
    identity=app.get('/v1/tiktok/connection').json()
    assert identity['connection']['displayName']=='UK Creator'
    assert identity['capabilities']['IDENTITY']=='AVAILABLE'
    assert identity['connection']['grantedScopes']==['user.info.basic']
    assert provider.exchange_verifiers==[None]


def test_adversarial_authority_binding_and_idempotency(system):
    c = authenticate(system)
    experiment = setup_authority(c)
    assert post(c,'experiments',{**experiment,'opportunity_id':'unknown'}).status_code == 403
    assert post(c,'experiments',experiment).status_code == 200
    assert event(c,'PUBLISHED','video-1').status_code == 403
    assert post(c,'product-claims',{'claim_id':'unknown','product_id':'product-1','text':'unsupported',
        'state':'UNKNOWN'}).status_code == 200
    assert post(c,'creatives',{'creative_id':'creative-1','experiment_id':'EXP-001','content':'unsafe',
        'claim_ids':['unknown'],'evidence_ref':'operator:creative:1'}).status_code == 403
    claim, creative, approval, packet = prepare_launch_existing(c)
    assert post(c,'creatives',{**creative,'content':'changed'}).status_code == 409
    assert post(c,'creative-approvals',{**approval,'evidence_ref':'operator:changed'}).status_code == 409
    assert post(c,'launch-intents',packet).json()['duplicate'] is True
    assert event(c,'ORDER_CREATED','order-1',parent='missing').status_code == 409
    published = event(c,'PUBLISHED','video-1')
    assert published.status_code == 200
    assert event(c,'PUBLISHED','video-1').json()['duplicate'] is True
    assert event(c,'PUBLISHED','video-2').status_code == 409
    assert event(c,'ORDER_CREATED','order-1',parent='wrong').status_code == 409
    assert event(c,'ORDER_CREATED','order-1',parent='video-1').status_code == 200
    assert event(c,'DELIVERED','delivery-1',parent='order-1').status_code == 200
    assert event(c,'COMMISSION_SETTLED','settle-1',parent='missing',amount='5.00').status_code == 409
    assert event(c,'COMMISSION_SETTLED','settle-1',parent='order-1',amount='0.99').status_code == 200
    assert event(c,'COMMISSION_SETTLED','settle-1',parent='order-1',amount='0.99').json()['duplicate'] is True
    assert event(c,'COMMISSION_SETTLED','settle-1',parent='order-1',amount='5.00').status_code == 409
    assert post(c,'costs',{'experiment_id':'EXP-001','amount_gbp':'0.00','evidence_ref':'operator:cost:0'}).status_code == 200
    assert c.get('/v1/portfolio').json()['experiments'][0]['realizedContributionGbp']=='0.99'
    assert c.get('/v1/portfolio').json()['experiments'][0]['firstPoundCandidate'] is False
    assert event(c,'REFUNDED','refund-1',parent='missing',amount='2.00').status_code == 409
    assert event(c,'REFUNDED','refund-1',parent='settle-1',amount='2.00').status_code == 200
    assert c.get('/v1/portfolio').json()['experiments'][0]['realizedContributionGbp']=='-1.01'
    assert post(c,'cost-adjustments',{'adjustment_id':'adjustment-1','experiment_id':'EXP-001',
        'amount_gbp':'1.00','evidence_ref':'operator:cost:extra'}).json()['duplicate'] is False
    assert post(c,'cost-adjustments',{'adjustment_id':'adjustment-1','experiment_id':'EXP-001',
        'amount_gbp':'1.00','evidence_ref':'operator:cost:extra'}).json()['duplicate'] is True
    assert post(c,'cost-adjustments',{'adjustment_id':'adjustment-1','experiment_id':'EXP-001',
        'amount_gbp':'2.00','evidence_ref':'operator:cost:extra'}).status_code == 409
    assert post(c,'capital-authority',{'authority_id':'capital-2','available_capital_gbp':'0.00',
        'capital_limit_gbp':'0.00','loss_limit_gbp':'0.00','minimum_allocation_score':100,
        'evidence_ref':'operator:capital:2'}).status_code == 200
    assert event(c,'PUBLISHED','video-3').status_code == 403
    assert c.get('/v1/portfolio').json()['experiments'][0]['realizedContributionGbp']=='-2.01'


def prepare_launch_existing(c):
    claim = {'claim_id':'claim-1','product_id':'product-1','text':'Demonstrated feature',
        'state':'SUPPORTED','evidence_ref':'operator:claim:1'}
    assert post(c,'product-claims',claim).status_code == 200
    creative = {'creative_id':'creative-1','experiment_id':'EXP-001','content':'Human-reviewed video draft',
        'claim_ids':['claim-1'],'evidence_ref':'operator:creative:1'}
    assert post(c,'creatives',creative).status_code == 200
    approval = {'approval_id':'approval-1','experiment_id':'EXP-001','creative_id':'creative-1',
        'evidence_ref':'operator:approval:1'}
    assert post(c,'creative-approvals',approval).status_code == 200
    packet = {'packet_id':'packet-1','experiment_id':'EXP-001','approval_id':'approval-1'}
    assert post(c,'launch-intents',packet).status_code == 200
    return claim, creative, approval, packet


@pytest.mark.parametrize(('capital', 'loss', 'allocation', 'risk'), [
    ('2.00','5.00','3.00','2.00'), ('8.00','1.00','3.00','2.00')])
def test_capital_and_loss_are_calculated_server_side(system, capital, loss, allocation, risk):
    c = authenticate(system)
    experiment = setup_authority(c, capital=capital, loss=loss, allocation=allocation, risk=risk)
    assert post(c,'experiments',experiment).status_code == 403
    assert c.get('/v1/capital-authority').json()['status']=='ACTIVE'


def test_late_product_truth_block_revokes_unpublished_intent(system):
    c = authenticate(system)
    prepare_launch(c,setup_authority(c))
    assert post(c,'product-claims',{'claim_id':'claim-block','product_id':'product-1',
        'text':'Demonstrated feature','state':'BLOCKED'}).status_code == 200
    assert event(c,'PUBLISHED','video-blocked').status_code == 403
    assert post(c,'launch-intents',{'packet_id':'packet-1','experiment_id':'EXP-001',
        'approval_id':'approval-1'}).status_code == 403


@pytest.mark.parametrize('field', ['access_expires_at','manual_verified_at'])
def test_expired_identity_or_manual_authority_blocks_new_writes(system, field):
    c = authenticate(system)
    with Session(create_engine(system[0])) as session:
        account = session.scalar(select(TikTokConnection))
        setattr(account,field,datetime.now(timezone.utc)-timedelta(days=31))
        session.commit()
    result = post(c,'capital-authority',{'authority_id':'expired','available_capital_gbp':'1.00',
        'capital_limit_gbp':'1.00','loss_limit_gbp':'1.00','minimum_allocation_score':60,
        'evidence_ref':'operator:expired:1'})
    assert result.status_code == 403


def test_invalid_inputs_and_unauthorized_operator_fail_closed(system):
    c = authenticate(system)
    other = system[2]()
    assert other.get('/v1/capital-authority').status_code == 401
    assert other.post('/v1/capital-authority',json={}).status_code == 401
    assert post(c,'capital-authority',{'authority_id':'bad','available_capital_gbp':'NaN',
        'capital_limit_gbp':'1.00','loss_limit_gbp':'1.00','minimum_allocation_score':60,
        'evidence_ref':'operator:bad:1'}).status_code == 422
    assert post(c,'product-claims',{'claim_id':'bad','product_id':'nonexistent','text':'invented',
        'state':'VERIFIED'}).status_code == 422
