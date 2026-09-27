import { validateCreativeStrategy, type CreativeContext, type CreativeStrategy } from '../ai/creativeStrategist';
import { assertPublishableClaims, type ProductTruthRecord } from './productTruth';
import type { FrozenExp001Candidate } from './realExp001Freeze';

export type CreativeEvidencePack = {
  packId:string;
  experimentId:string;
  decisionId:string;
  productId:string;
  listingRef:string;
  hypothesis:string;
  variableUnderTest:string;
  strategy:CreativeStrategy;
  claimEvidence:Array<{claim:string;sourceRefs:string[]}>;
  humanApprovalRequired:true;
  publishable:false;
  createdAt:string;
};

export function buildCreativeEvidencePack(
 frozen:FrozenExp001Candidate,
 truth:ProductTruthRecord,
 context:CreativeContext,
 strategy:CreativeStrategy,
 createdAt:string,
):CreativeEvidencePack {
 if(!Number.isFinite(Date.parse(createdAt))) throw new Error('createdAt must be a valid timestamp');
 if(truth.productId!==frozen.product.productId) throw new Error('ProductTruth/product trace mismatch');
 if(context.experimentId!==frozen.experiment.experimentId) throw new Error('Creative context/experiment trace mismatch');
 if(context.hypothesis!==frozen.experiment.hypothesis||context.variableUnderTest!==frozen.experiment.variableUnderTest) throw new Error('Creative context cannot rewrite frozen experiment');
 const validated=validateCreativeStrategy(strategy,context);
 assertPublishableClaims(truth,validated.claimsUsed);
 const claimEvidence=validated.claimsUsed.map(claim=>{
   const refs=truth.claims.filter(x=>x.text===claim&&(x.state==='VERIFIED'||x.state==='SUPPORTED')).flatMap(x=>x.sourceRefs);
   if(refs.length===0) throw new Error(`Claim lacks evidence reference: ${claim}`);
   return {claim,sourceRefs:[...new Set(refs)]};
 });
 return Object.freeze({
   packId:`CEP-${frozen.experiment.experimentId}`,experimentId:frozen.experiment.experimentId,decisionId:frozen.experiment.decisionId,
   productId:frozen.product.productId,listingRef:frozen.product.listingRef,hypothesis:frozen.experiment.hypothesis,
   variableUnderTest:frozen.experiment.variableUnderTest,strategy:structuredClone(validated),claimEvidence,
   humanApprovalRequired:true,publishable:false,createdAt,
 });
}
