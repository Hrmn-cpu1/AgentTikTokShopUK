import type {RealProductRecord} from './realProductIntake';
import type {OpportunityAuthority} from './opportunityAuthority';
import type {CapitalAuthority} from './capitalAuthority';
import type {OpportunityEvidenceDossier} from './opportunityEvidenceDossier';
import {evaluateEvidenceBackedOpportunity} from './evidenceBackedOpportunity';

export function evaluatePersistedRealOpportunity(args:{product:RealProductRecord|null;dossier:OpportunityEvidenceDossier|null;authority:OpportunityAuthority;capital:CapitalAuthority|null;nowIso:string}){
 if(!args.product||!args.dossier||!args.capital)return null;
 return evaluateEvidenceBackedOpportunity(args.product,args.dossier,args.nowIso,args.authority,args.capital);
}
