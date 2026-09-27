import {buildDecisionMoneyTrace} from './decisionMoney';import {proveFirstPound,type FirstPoundProof} from './firstPoundProof';import {loadFrozenExp001} from './frozenExp001Store';import {loadExperimentCost} from './experimentCostTruth';import {BrowserBusinessTruthStore} from './businessTruthStore';import type {PublishedLaunch} from './publishedResultCapture';
import {loadLaunchPacket} from './launchPacketStore';import {loadCreativeEvidencePack} from './creativeEvidencePackStore';import {loadCreativeApproval} from './creativeApproval';
// Persist facts and derive conclusions anew so a later refund revokes stale proof.
export function deriveFirstPoundFromBusinessTruth(storage:Storage,now:string):FirstPoundProof|null{
 if(!Number.isFinite(Date.parse(now)))throw new Error('Invalid proof evaluation timestamp');
 const frozen=loadFrozenExp001(storage),cost=loadExperimentCost(storage),packet=loadLaunchPacket(storage);
 const creative=loadCreativeEvidencePack(storage),approval=creative?loadCreativeApproval(storage,creative):null;
 if(!frozen||!cost||!packet||!creative||!approval||!packet.readyForManualPublish||!frozen.decisionTruth)return null;
 const {experiment,product}=frozen;
 if(cost.experimentId!==experiment.experimentId||packet.experimentId!==experiment.experimentId||packet.decisionId!==experiment.decisionId||packet.productId!==product.productId||packet.creativePackId!==creative.packId||creative.decisionId!==experiment.decisionId||approval.creativePackId!==packet.creativePackId)return null;
 const events=new BrowserBusinessTruthStore(storage).load().events.filter(e=>e.experimentId===experiment.experimentId);
 const pubs=events.filter(e=>e.type==='PUBLISHED'&&e.actionId===packet.packetId&&e.externalEventId&&e.evidenceRef);
 if(pubs.length!==1||events.some(e=>e.type!=='PUBLISHED'&&e.actionId!==packet.packetId)||
   !events.some(e=>e.type==='ORDER_CREATED')||!events.some(e=>e.type==='DELIVERED')||
   !events.some(e=>e.type==='COMMISSION_SETTLED'))return null;
 const pub=pubs[0];
 const publication:PublishedLaunch={packetId:packet.packetId,experimentId:experiment.experimentId,creativeId:packet.creativeId,externalPublicationId:pub.externalEventId,publishedAt:pub.occurredAt,evidenceRef:pub.evidenceRef!};
 const trace=buildDecisionMoneyTrace({decisionId:experiment.decisionId,experimentId:experiment.experimentId,opportunityId:experiment.opportunityId,...frozen.decisionTruth,experimentCostsGbp:cost.amountGbp,events,performance:{attentionValidated:null,intentValidated:null,conversionValidated:events.some(e=>e.type==='ORDER_CREATED')?true:null,fulfillmentValidated:events.some(e=>e.type==='DELIVERED')?true:null,repeatedProfitableCycles:0,supplyAvailable:product.available,creativeFatigued:false}});
 const refs=[...frozen.evidenceRefs,approval.approvalId,cost.evidenceRef,...events.map(e=>e.evidenceRef).filter((x):x is string=>Boolean(x))];
 const lastObserved=[cost.observedAt,...events.map(e=>e.occurredAt)].sort().at(-1)!;
 return proveFirstPound(trace,publication,refs,lastObserved);
}
