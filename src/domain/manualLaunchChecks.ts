import type {FrozenExp001Candidate} from './realExp001Freeze';
import type {CreativeEvidencePack} from './creativeEvidencePack';
import type {AssistedExecutionInput} from './assistedExecution';
import {loadRealOpportunityProjection} from './realOpportunityProjection';
import {BrowserRealityEvidenceStore,hydrateRealityRegistry} from './realityPersistence';
import {loadProductTruth} from './productTruthStore';
import {assertPublishableClaims} from './productTruth';
import {loadCreativeApproval} from './creativeApproval';
import {readExecutionEnabled} from './realityCutoverGuard';

export function deriveManualLaunchChecks(storage:Storage,frozen:FrozenExp001Candidate,creative:CreativeEvidencePack,now:string):Omit<AssistedExecutionInput,'decisionId'|'experimentId'|'creativeId'>{
 const projection=loadRealOpportunityProjection(storage,now);
 const registry=hydrateRealityRegistry(new BrowserRealityEvidenceStore(storage));
 const verified=(subject:Parameters<typeof registry.resolve>[0])=>registry.resolve(subject,now).state==='VERIFIED';
 const capital=projection.capital?.limits;
 const truth=loadProductTruth(storage);
 let claimsValid=false;
 if(truth?.productId===frozen.product.productId&&creative.productId===truth.productId){
  try{assertPublishableClaims(truth,creative.strategy.claimsUsed);
   claimsValid=creative.claimEvidence.every(item=>item.sourceRefs.length>0&&creative.strategy.claimsUsed.includes(item.claim));
  }catch{/* Missing or blocked claims fail closed. */}
 }
 const experimentReady=projection.result?.allocation.decision==='ALLOCATE'&&
  projection.product?.productId===frozen.product.productId&&projection.product?.listingRef===frozen.product.listingRef&&
  creative.experimentId===frozen.experiment.experimentId&&creative.decisionId===frozen.experiment.decisionId&&
  verified('PAYOUT_METHOD')&&verified('PRODUCT_FRESHNESS')&&verified('SUPPLY')&&
  Boolean(projection.product?.available);
 return {
  marketEligibility:projection.authority.marketEligible?'ELIGIBLE':'BLOCKED',
  experimentReady,
  claimsValid,
  humanApproved:loadCreativeApproval(storage,creative)!==null,
  executionEnabled:readExecutionEnabled(storage),
  withinCapitalLimit:Boolean(capital)&&frozen.experiment.capitalLimit<=capital!.capitalLimit&&frozen.experiment.capitalLimit<=capital!.availableCapital,
  withinLossLimit:Boolean(capital)&&frozen.experiment.lossLimit<=capital!.lossLimit,
  accountRiskAcceptable:projection.authority.accountRiskAcceptable,
 };
}
