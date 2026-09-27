import {buildEvidenceBackedOpportunityInput} from './evidenceBackedOpportunity';
import {freezeRealExp001} from './realExp001Freeze';
import {loadRealOpportunityProjection} from './realOpportunityProjection';
import {loadFrozenExp001,saveFrozenExp001} from './frozenExp001Store';

export function freezePersistedExp001(storage:Storage,nowIso:string){
 const existing=loadFrozenExp001(storage);if(existing)return existing;
 const p=loadRealOpportunityProjection(storage,nowIso);
 if(!p.product||!p.dossier||!p.capital||!p.result)throw new Error('EXP-001 requires complete persisted opportunity truth');
 const input=buildEvidenceBackedOpportunityInput(p.product,p.dossier,nowIso,p.authority,p.capital);
 if(!input)throw new Error('EXP-001 governed input unavailable');
 const frozen=freezeRealExp001(input,p.result,nowIso,p.dossier.evidenceRefs);
 return saveFrozenExp001(storage,frozen);
}
