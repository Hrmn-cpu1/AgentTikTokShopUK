import type { CreativeEvidencePack } from './creativeEvidencePack';
import type { FrozenExp001Candidate } from './realExp001Freeze';
import { prepareAssistedExecution, type AssistedExecutionInput } from './assistedExecution';

export function buildLaunchPacket(
  frozen: FrozenExp001Candidate,
  creative: CreativeEvidencePack,
  creativeId: string,
  execution: Omit<AssistedExecutionInput, 'decisionId' | 'experimentId' | 'creativeId'>,
  createdAt: string,
) {
  if (!creativeId.trim()) throw new Error('creativeId is required');
  if (!Number.isFinite(Date.parse(createdAt))) throw new Error('createdAt must be valid');
  if (creative.experimentId !== frozen.experiment.experimentId || creative.productId !== frozen.product.productId) {
    throw new Error('Launch trace mismatch');
  }
  const plan = prepareAssistedExecution({
    decisionId: frozen.experiment.decisionId,
    experimentId: frozen.experiment.experimentId,
    creativeId,
    ...execution,
  });
  return {
    packetId: 'LP-' + frozen.experiment.experimentId + '-' + creativeId,
    decisionId: frozen.experiment.decisionId,
    experimentId: frozen.experiment.experimentId,
    creativeId,
    productId: frozen.product.productId,
    listingRef: frozen.product.listingRef,
    creativePackId: creative.packId,
    idempotencyKey: plan.idempotencyKey,
    manualSteps: plan.manualSteps,
    evidenceRefs: [...new Set([...frozen.evidenceRefs, ...creative.claimEvidence.flatMap(x => x.sourceRefs)])],
    readyForManualPublish: plan.ready,
    blockedReasons: plan.blockedReasons,
    externalPublicationId: null,
    createdAt,
  };
}
