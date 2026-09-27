import type {CreativeContext,CreativeStrategy} from '../ai/creativeStrategist';
import type {ProductTruthRecord} from './productTruth';
import type {FrozenExp001Candidate} from './realExp001Freeze';
import {buildCreativeEvidencePack} from './creativeEvidencePack';

export function buildCreativeContextFromTruth(frozen:FrozenExp001Candidate,truth:ProductTruthRecord):CreativeContext{
 if(truth.productId!==frozen.product.productId)throw new Error('ProductTruth/product trace mismatch');
 const by=(state:string)=>truth.claims.filter(x=>x.state===state).map(x=>x.text);
 return {experimentId:frozen.experiment.experimentId,hypothesis:frozen.experiment.hypothesis,variableUnderTest:frozen.experiment.variableUnderTest,productName:frozen.product.productName,creatorArchetype:'practical demonstrator',offer:'TikTok Shop affiliate offer',productTruth:{verifiedFacts:by('VERIFIED'),supportedClaims:by('SUPPORTED'),unsupportedClaims:by('UNKNOWN'),prohibitedClaims:by('BLOCKED')},winnerPatterns:['show product result early'],failurePatterns:['long generic intro','unsupported claims']};
}
export function ingestCreativeStrategy(frozen:FrozenExp001Candidate,truth:ProductTruthRecord,strategy:CreativeStrategy,createdAt:string){
 const context=buildCreativeContextFromTruth(frozen,truth);
 return buildCreativeEvidencePack(frozen,truth,context,strategy,createdAt);
}
