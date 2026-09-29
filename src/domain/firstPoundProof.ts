import type { PublishedLaunch } from './publishedResultCapture';
import type { DecisionMoneyTrace } from './decisionMoney';

export type FirstPoundProof = {
 status:'PROVEN'|'NOT_PROVEN';
 decisionId:string; experimentId:string; opportunityId:string; creativeId:string;
 externalPublicationId:string;
 settledCommissionGbp:number|null; experimentCostsGbp:number; realizedContributionGbp:number|null;
 evidenceRefs:string[];
 positiveContributionProven:boolean;
 repeatableWinnerProven:false;
 reason:string;
 provenAt:string;
};

export function proveFirstPound(
 trace:DecisionMoneyTrace,
 publication:PublishedLaunch,
 evidenceRefs:string[],
 provenAt:string,
):FirstPoundProof {
 if(!Number.isFinite(Date.parse(provenAt))) throw new Error('provenAt must be a valid timestamp');
 if(trace.decisionTruth.experimentId!==publication.experimentId) throw new Error('Decision/publication experiment trace mismatch');
 if(!publication.externalPublicationId.trim()) throw new Error('Real publication id is required');
 const refs=[...new Set([publication.evidenceRef,...evidenceRefs].filter(Boolean))];
 if(refs.length===0) throw new Error('First pound proof requires evidence provenance');
 const contribution=trace.economicTruth.realizedContributionGbp;
 const positiveContributionProven=trace.decisionTruth.executable&&trace.executionTruth.economicTruthKnown&&
   trace.economicTruth.settledCommissionGbp!==null&&contribution!==null&&contribution>0;
 const proven=positiveContributionProven&&contribution!==null&&contribution>=1;
 return Object.freeze({
   status:proven?'PROVEN':'NOT_PROVEN',decisionId:trace.decisionTruth.decisionId,experimentId:trace.decisionTruth.experimentId,
   opportunityId:trace.decisionTruth.opportunityId,creativeId:publication.creativeId,externalPublicationId:publication.externalPublicationId,
   settledCommissionGbp:trace.economicTruth.settledCommissionGbp,experimentCostsGbp:trace.economicTruth.experimentCostsGbp,
   realizedContributionGbp:contribution,evidenceRefs:refs,positiveContributionProven,repeatableWinnerProven:false,
   reason:proven?'At least £1.00 of realized contribution is backed by net settled commission, observed cost and complete execution trace.':positiveContributionProven?'Positive realized contribution is proven, but it has not yet reached £1.00.':'Positive settled realized contribution has not been proven.',
   provenAt,
 });
}
