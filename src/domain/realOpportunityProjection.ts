import {BrowserRealityEvidenceStore,hydrateRealityRegistry} from './realityPersistence';
import {readExecutionEnabled} from './realityCutoverGuard';
import {loadCapitalAuthority} from './capitalAuthority';
import {loadOpportunityEvidence} from './opportunityEvidenceStore';
import {loadRealProduct} from './realProductStore';
import {resolveOpportunityAuthority} from './opportunityAuthority';
import {evaluatePersistedRealOpportunity} from './realOpportunityControl';

export function loadRealOpportunityProjection(storage:Storage,nowIso:string){
 const product=loadRealProduct(storage);
 const dossier=loadOpportunityEvidence(storage);
 const capital=loadCapitalAuthority(storage);
 const registry=hydrateRealityRegistry(new BrowserRealityEvidenceStore(storage));
 const authority=resolveOpportunityAuthority(registry,nowIso,{executionEnabled:readExecutionEnabled(storage),withinCapitalLimit:true,withinLossLimit:true,humanApproved:false,claimsValid:true});
 const result=evaluatePersistedRealOpportunity({product,dossier,authority,capital,nowIso});
 const blockers:string[]=[];
 if(!product)blockers.push('REAL_PRODUCT:MISSING');
 if(!dossier)blockers.push('OPPORTUNITY_EVIDENCE:MISSING');
 else if(dossier.state!=='READY')blockers.push(...dossier.missing.map(x=>'EVIDENCE:'+x));
 if(!capital)blockers.push('CAPITAL_AUTHORITY:MISSING');
 blockers.push(...authority.blockers);
 if(!authority.policyAllowed)blockers.push('POLICY:NOT_ALLOWED');
 return {product,dossier,capital,authority,result,blockers:[...new Set(blockers)]};
}
