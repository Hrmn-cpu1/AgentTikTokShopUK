"""Deterministic, process-local provider simulator and evidence reconciliation.

This module has no HTTP endpoint and performs no network I/O. It exercises the
existing Action Contract, Effect Ledger, and fenced outbox with a disposable fake
provider for tests/internal engineering only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from .action_effect_models import ActionContract, EffectEvidence, EffectLedger
from .action_effects import (OutboxLeaseIdentity, ReconciliationRequired,
    mark_effect_unknown_before_provider_io, persist_ambiguous_provider_outcome,
    persist_provider_acknowledgement, persist_safe_provider_no_effect,
    record_effect_evidence, utcnow)


class SendScenario(str, Enum):
    SUCCESS_ACK = "SUCCESS_ACK"
    TIMEOUT_BEFORE_ACCEPT = "TIMEOUT_BEFORE_ACCEPT"
    TIMEOUT_AFTER_ACCEPT = "TIMEOUT_AFTER_ACCEPT"
    CONNECTION_DROP_AFTER_SEND = "CONNECTION_DROP_AFTER_SEND"
    PROVIDER_REJECT = "PROVIDER_REJECT"
    RATE_LIMIT = "RATE_LIMIT"
    TEMPORARY_5XX_BEFORE_SEND = "TEMPORARY_5XX_BEFORE_SEND"
    TEMPORARY_5XX_AFTER_SEND = "TEMPORARY_5XX_AFTER_SEND"
    DUPLICATE_REQUEST_WITH_IDEMPOTENCY = "DUPLICATE_REQUEST_WITH_IDEMPOTENCY"
    DUPLICATE_REQUEST_WITHOUT_IDEMPOTENCY = "DUPLICATE_REQUEST_WITHOUT_IDEMPOTENCY"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    PROVIDER_REFERENCE_MISMATCH = "PROVIDER_REFERENCE_MISMATCH"


class ObservationScenario(str, Enum):
    UNAVAILABLE = "OBSERVATION_UNAVAILABLE"
    ZERO_MATCHES = "OBSERVATION_NO_MATCH"
    ONE_MATCH = "OBSERVATION_MATCH"
    MULTIPLE_MATCHES = "OBSERVATION_MULTIPLE_MATCHES"
    MISMATCH = "OBSERVATION_MISMATCH"
    REFERENCE_MISMATCH = "PROVIDER_REFERENCE_MISMATCH"


class SimulatedProcessCrash(RuntimeError):
    """A deliberate crash point. The committed database state is left intact."""


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_idempotency: bool = True
    supports_status_lookup: bool = True
    supports_observation: bool = True
    supports_provider_reference: bool = True
    supports_safe_retry_before_effect: bool = True


@dataclass(frozen=True)
class FrozenProviderRequest:
    action_contract_id: str
    effect_id: str
    effect_key: str
    provider: str
    operation: str
    artifact_id: str
    artifact_sha256: str
    target_account_id: str | None
    business_parameters_digest: str
    request_digest: str
    contract_digest: str
    unique_marker: str


@dataclass(frozen=True)
class ProviderResponse:
    result_class: str
    response_digest: str
    accepted: bool
    provider_reference: str | None = None
    ambiguous: bool = False
    retry_after: timedelta | None = None
    malformed: bool = False


@dataclass(frozen=True)
class ObservationCandidate:
    provider: str
    operation: str
    effect_id: str
    action_contract_id: str
    contract_digest: str
    artifact_id: str
    artifact_sha256: str
    target_account_id: str | None
    business_parameters_digest: str
    request_digest: str
    unique_marker: str
    provider_reference: str


@dataclass(frozen=True)
class ObservationResult:
    classification: str
    candidates: tuple[ObservationCandidate, ...] = ()
    observed_at: datetime = datetime.min.replace(tzinfo=timezone.utc)


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def frozen_request(session: Session, effect_id: str) -> FrozenProviderRequest:
    effect = session.scalar(select(EffectLedger).where(EffectLedger.effect_id == effect_id))
    if effect is None:
        raise KeyError(effect_id)
    contract = session.get(ActionContract, effect.action_contract_id)
    if contract is None:
        raise RuntimeError("effect has no immutable Action Contract")
    if (effect.provider != "PROVIDER_LAB" or contract.provider != "PROVIDER_LAB" or
            contract.action_type != "PROVIDER_LAB_TEST" or
            contract.required_capability != "provider.lab.test"):
        raise ValueError("Provider Lab refuses non-lab action/provider/capability")
    if (contract.request_digest != effect.request_digest or
            contract.artifact_sha256 != effect.artifact_sha256):
        raise RuntimeError("effect and frozen Action Contract disagree")
    return FrozenProviderRequest(
        action_contract_id=contract.action_contract_id, effect_id=effect.effect_id,
        effect_key=effect.effect_key, provider=effect.provider, operation=effect.operation,
        artifact_id=contract.artifact_id, artifact_sha256=contract.artifact_sha256,
        target_account_id=contract.target_account_id,
        business_parameters_digest=contract.business_parameters_digest,
        request_digest=contract.request_digest, contract_digest=contract.request_digest,
        unique_marker=effect.effect_key)


class DeterministicProviderLab:
    """A fake provider with a separate in-memory effect store and read channel."""

    provider = "PROVIDER_LAB"

    def __init__(self, capabilities: ProviderCapabilities | None = None):
        self.capabilities = capabilities or ProviderCapabilities()
        self._lock = threading.Lock()
        self._records: list[ObservationCandidate] = []
        self._by_idempotency_key: dict[str, ObservationCandidate] = {}
        self.send_calls = 0
        self._sequence = 0

    @property
    def records(self) -> tuple[ObservationCandidate, ...]:
        with self._lock:
            return tuple(self._records)

    def _accept(self, request: FrozenProviderRequest) -> ObservationCandidate:
        key = request.unique_marker
        if self.capabilities.supports_idempotency and key in self._by_idempotency_key:
            return self._by_idempotency_key[key]
        self._sequence += 1
        reference = f"plab-{request.effect_id[:12]}-{self._sequence:04d}"
        candidate = ObservationCandidate(
            provider=request.provider, operation=request.operation, effect_id=request.effect_id,
            action_contract_id=request.action_contract_id, contract_digest=request.contract_digest,
            artifact_id=request.artifact_id, artifact_sha256=request.artifact_sha256,
            target_account_id=request.target_account_id,
            business_parameters_digest=request.business_parameters_digest,
            request_digest=request.request_digest, unique_marker=request.unique_marker,
            provider_reference=reference)
        self._records.append(candidate)
        if self.capabilities.supports_idempotency:
            self._by_idempotency_key[key] = candidate
        return candidate

    def send(self, request: FrozenProviderRequest, scenario: SendScenario, *,
             crash_after_accept: bool = False) -> ProviderResponse:
        """Simulate one provider request. This method never opens a socket."""
        scenario = SendScenario(scenario)
        with self._lock:
            self.send_calls += 1
            if scenario == SendScenario.TIMEOUT_BEFORE_ACCEPT:
                return self._response("PROVIDER_TIMEOUT_BEFORE_ACCEPT", accepted=False)
            if scenario == SendScenario.PROVIDER_REJECT:
                return self._response("PROVIDER_REJECTED", accepted=False)
            if scenario == SendScenario.RATE_LIMIT:
                return self._response("PROVIDER_RATE_LIMIT", accepted=False,
                                      retry_after=timedelta(seconds=30))
            if scenario == SendScenario.TEMPORARY_5XX_BEFORE_SEND:
                return self._response("PROVIDER_5XX_BEFORE_SEND", accepted=False,
                                      retry_after=timedelta(seconds=5))

            if scenario == SendScenario.DUPLICATE_REQUEST_WITH_IDEMPOTENCY:
                if not self.capabilities.supports_idempotency:
                    return self._response("PROVIDER_IDEMPOTENCY_UNAVAILABLE", accepted=False)
                # Two deliveries model a duplicate network request. Provider-side
                # idempotency returns the same single logical record.
                first = self._accept(request)
                second = self._accept(request)
                assert first == second
                return self._response("PROVIDER_ACKNOWLEDGED", accepted=True,
                    provider_reference=first.provider_reference if self.capabilities.supports_provider_reference else None)

            candidate = self._accept(request)
            if crash_after_accept:
                raise SimulatedProcessCrash("crash after provider accepted, before response")
            if scenario in {SendScenario.TIMEOUT_AFTER_ACCEPT,
                            SendScenario.CONNECTION_DROP_AFTER_SEND,
                            SendScenario.TEMPORARY_5XX_AFTER_SEND,
                            SendScenario.DUPLICATE_REQUEST_WITHOUT_IDEMPOTENCY}:
                result = {
                    SendScenario.TIMEOUT_AFTER_ACCEPT: "PROVIDER_TIMEOUT_AFTER_ACCEPT",
                    SendScenario.CONNECTION_DROP_AFTER_SEND: "PROVIDER_CONNECTION_DROP_AFTER_SEND",
                    SendScenario.TEMPORARY_5XX_AFTER_SEND: "PROVIDER_5XX_AFTER_SEND",
                    SendScenario.DUPLICATE_REQUEST_WITHOUT_IDEMPOTENCY: "PROVIDER_DUPLICATE_UNPROTECTED",
                }[scenario]
                return self._response(result, accepted=True, ambiguous=True)
            if scenario == SendScenario.MALFORMED_RESPONSE:
                return self._response("PROVIDER_MALFORMED_RESPONSE", accepted=True,
                                      ambiguous=True, malformed=True)
            if scenario == SendScenario.PROVIDER_REFERENCE_MISMATCH:
                return self._response("PROVIDER_ACKNOWLEDGED", accepted=True,
                                      provider_reference="plab-wrong-reference")
            return self._response("PROVIDER_ACKNOWLEDGED", accepted=True,
                provider_reference=candidate.provider_reference if self.capabilities.supports_provider_reference else None)

    def _response(self, result_class: str, *, accepted: bool,
                  provider_reference: str | None = None,
                  ambiguous: bool = False, retry_after: timedelta | None = None,
                  malformed: bool = False) -> ProviderResponse:
        safe = {"provider": self.provider, "result": result_class, "accepted": accepted,
                "providerReference": provider_reference, "ambiguous": ambiguous,
                "malformed": malformed}
        return ProviderResponse(result_class, _digest(safe), accepted,
                                provider_reference, ambiguous, retry_after, malformed)

    def observe(self, request: FrozenProviderRequest,
                scenario: ObservationScenario) -> ObservationResult:
        """Independent read path; it never sends or retries an effect."""
        scenario = ObservationScenario(scenario)
        now = datetime.now(timezone.utc)
        if not self.capabilities.supports_observation or not self.capabilities.supports_status_lookup:
            return ObservationResult("OBSERVATION_UNAVAILABLE", observed_at=now)
        if scenario == ObservationScenario.REFERENCE_MISMATCH and not self.capabilities.supports_provider_reference:
            return ObservationResult("MISMATCH", observed_at=now)
        with self._lock:
            matching = [r for r in self._records if r.unique_marker == request.unique_marker]
        if not self.capabilities.supports_provider_reference:
            matching = [ObservationCandidate(**{**asdict(row), "provider_reference": ""})
                        for row in matching]
        if scenario == ObservationScenario.UNAVAILABLE:
            return ObservationResult("OBSERVATION_UNAVAILABLE", observed_at=now)
        if scenario == ObservationScenario.ZERO_MATCHES:
            return ObservationResult("ZERO_MATCHES", observed_at=now)
        if scenario == ObservationScenario.MULTIPLE_MATCHES:
            if not matching:
                return ObservationResult("ZERO_MATCHES", observed_at=now)
            return ObservationResult("MULTIPLE_MATCHES", tuple(matching + matching[:1]), now)
        if scenario == ObservationScenario.MISMATCH:
            if not matching:
                return ObservationResult("ZERO_MATCHES", observed_at=now)
            row = matching[0]
            altered = ObservationCandidate(**{**asdict(row), "artifact_sha256": "0" * 64})
            return ObservationResult("ONE_MATCH", (altered,), now)
        if scenario == ObservationScenario.REFERENCE_MISMATCH:
            if not matching:
                return ObservationResult("ZERO_MATCHES", observed_at=now)
            row = matching[0]
            altered = ObservationCandidate(**{**asdict(row), "provider_reference": "plab-other-reference"})
            return ObservationResult("ONE_MATCH", (altered,), now)
        return ObservationResult("ONE_MATCH" if len(matching) == 1 else
            "MULTIPLE_MATCHES" if len(matching) > 1 else "ZERO_MATCHES", tuple(matching), now)


def dispatch_provider_lab(session: Session, identity: OutboxLeaseIdentity,
                          provider: DeterministicProviderLab, scenario: SendScenario, *,
                          crash_at: str | None = None,
                          retry_delay_override: timedelta | None = None,
                          retry_authorized: bool = False) -> ProviderResponse | None:
    """Consume a real fenced outbox item; commit UNKNOWN before simulator I/O."""
    if crash_at == "BEFORE_PROVIDER_BOUNDARY":
        raise SimulatedProcessCrash("crash before provider boundary")
    request = frozen_request(session, identity.effect_id)
    if provider.provider != request.provider:
        raise ValueError("simulator/provider mismatch")
    effect = session.get(EffectLedger, identity.effect_id)
    if effect is None or effect.state != "PREPARED" or effect.reconciliation_required:
        raise ReconciliationRequired("only a fresh PREPARED effect may enter dispatch")
    mark_effect_unknown_before_provider_io(session, identity)
    session.commit()  # durable uncertainty must precede the simulated send
    if crash_at in {"AFTER_UNKNOWN_COMMIT", "IMMEDIATELY_BEFORE_SEND"}:
        raise SimulatedProcessCrash("crash after UNKNOWN commit, before provider send")
    response = provider.send(request, SendScenario(scenario),
        crash_after_accept=crash_at == "AFTER_PROVIDER_ACCEPT")
    if crash_at == "BEFORE_RESPONSE_PERSISTENCE":
        raise SimulatedProcessCrash("crash after provider response, before database persistence")
    if response.malformed or response.ambiguous:
        persist_ambiguous_provider_outcome(session, identity,
            error_class=response.result_class, response_digest=response.response_digest)
        session.commit()
        return response
    if response.accepted:
        # A provider ACK/reference is only a dispatch observation, never CONFIRMED.
        persist_provider_acknowledgement(session, identity,
            provider_reference=response.provider_reference,
            response_digest=response.response_digest)
        session.commit()
        return response

    retry_after = response.retry_after if retry_authorized else None
    if retry_after is not None and not provider.capabilities.supports_safe_retry_before_effect:
        retry_after = None
    if retry_delay_override is not None:
        retry_after = retry_delay_override if (retry_authorized and
            provider.capabilities.supports_safe_retry_before_effect) else None
    failure_state = "REJECTED" if response.result_class == "PROVIDER_REJECTED" else "FAILED_BEFORE_EFFECT"
    persist_safe_provider_no_effect(session, identity, result_class=response.result_class,
        proof_digest=response.response_digest, retry_after=retry_after, failure_state=failure_state)
    session.commit()
    return response


def _candidate_matches(request: FrozenProviderRequest, candidate: ObservationCandidate,
                       expected_provider_reference: str | None,
                       require_provider_reference: bool) -> bool:
    required = (
        candidate.provider == request.provider,
        candidate.operation == request.operation,
        candidate.effect_id == request.effect_id,
        candidate.action_contract_id == request.action_contract_id,
        candidate.contract_digest == request.contract_digest,
        candidate.artifact_id == request.artifact_id,
        candidate.artifact_sha256 == request.artifact_sha256,
        candidate.target_account_id == request.target_account_id,
        candidate.business_parameters_digest == request.business_parameters_digest,
        candidate.request_digest == request.request_digest,
        candidate.unique_marker == request.unique_marker,
    )
    if require_provider_reference:
        required += (bool(candidate.provider_reference),)
    if expected_provider_reference is not None:
        required += (candidate.provider_reference == expected_provider_reference,)
    return all(required)


def reconcile_provider_lab(session: Session, effect_id: str,
                           provider: DeterministicProviderLab,
                           scenario: ObservationScenario, *,
                           fault_after_evidence: bool = False,
                           crash_before_evidence: bool = False) -> str:
    """Observe separately from send; atomically confirm only one exact match."""
    request = frozen_request(session, effect_id)
    effect = session.get(EffectLedger, effect_id)
    if effect is None:
        raise KeyError(effect_id)
    if effect.state not in {"UNKNOWN", "RECONCILIATION_REQUIRED"} or not effect.reconciliation_required:
        raise ReconciliationRequired("only an ambiguous effect can be reconciled")
    expected_provider_reference = effect.provider_reference
    observation = provider.observe(request, ObservationScenario(scenario))
    if crash_before_evidence:
        raise SimulatedProcessCrash("crash after observation read, before evidence persistence")
    candidates = observation.candidates
    classification = observation.classification
    if classification == "ONE_MATCH" and len(candidates) == 1:
        if not _candidate_matches(request, candidates[0], expected_provider_reference,
                                  provider.capabilities.supports_provider_reference):
            classification = "MISMATCH"
    elif classification == "ONE_MATCH" and len(candidates) != 1:
        classification = "MULTIPLE_MATCHES" if len(candidates) > 1 else "ZERO_MATCHES"
    elif classification == "MULTIPLE_MATCHES" and len(candidates) < 2:
        classification = "MISMATCH"

    evidence_payload = {
        "effectId": effect_id,
        "provider": request.provider,
        "observationType": classification,
        "observedAt": observation.observed_at.isoformat(),
        "contractDigest": request.contract_digest,
        "artifactId": request.artifact_id,
        "artifactSha256": request.artifact_sha256,
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    if len(candidates) == 1:
        evidence_ref = candidates[0].provider_reference or f"provider-lab://effect/{effect_id}"
    else:
        evidence_ref = f"provider-lab://observation/{classification.casefold()}"

    # Savepoint ensures injected failure after evidence cannot persist half-truth.
    with session.begin_nested():
        effect = session.scalar(select(EffectLedger).where(
            EffectLedger.effect_id == effect_id).with_for_update())
        if (effect is None or effect.state not in {"UNKNOWN", "RECONCILIATION_REQUIRED"} or
                not effect.reconciliation_required):
            raise ReconciliationRequired("effect changed while observation was being reconciled")
        evidence = record_effect_evidence(session, effect_id=effect_id,
            evidence_type="PROVIDER_LAB_RECONCILIATION", source=provider.provider,
            source_reference=evidence_ref, observed_at=observation.observed_at,
            payload=evidence_payload, classification="RECONCILIATION_RESULT")
        if classification != "ONE_MATCH":
            effect.state = "RECONCILIATION_REQUIRED"
            effect.reconciliation_required = True
            effect.updated_at = utcnow()
            session.flush()
            return classification
        if fault_after_evidence:
            raise SimulatedProcessCrash("crash after evidence insert before effect confirmation")
        effect.confirmation_evidence_id = evidence.evidence_id
        effect.provider_reference = candidates[0].provider_reference or None
        effect.state = "CONFIRMED"
        effect.reconciliation_required = False
        effect.confirmed_at = utcnow()
        effect.failure_class = None
        effect.updated_at = utcnow()
        session.flush()
    return "CONFIRMED"
