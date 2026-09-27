// Same-origin operator API. Provider credentials remain server-side.
export type PortfolioExperiment = {
  experimentId:string; decisionId:string; productId:string; creativeId:string;
  publicationObserved:boolean; netSettledGbp:string|null; observedCostGbp:string|null;
  realizedContributionGbp:string|null; firstPoundCandidate:boolean;
  commercialProof:'NOT_PROVEN'; source:'MANUAL_ASSERTION';
};
export type Portfolio = { experiments:PortfolioExperiment[]; commercialProof:'NOT_PROVEN'; authority:'SERVER_OBSERVATIONS_ONLY' };

export async function apiJson<T>(path:string, init?:RequestInit):Promise<T> {
  if(!path.startsWith('/v1/'))throw new Error('Invalid API path');
  let response:Response;
  try {response=await fetch(path,{credentials:'same-origin',cache:'no-store',...init})}
  catch {throw new Error('BACKEND UNAVAILABLE')}
  if(!response.ok){
    const body:unknown=await response.json().catch(()=>null);
    const detail=typeof body==='object'&&body!==null&&'detail' in body&&typeof body.detail==='string'?
      body.detail.slice(0,200):null;
    throw new Error(response.status===401?'Operator session expired':
      response.status===503?'Server configuration required':detail??`Backend rejected request (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function operatorCsrf():string {
  return decodeURIComponent(document.cookie.split('; ').find(value=>value.startsWith('operator_csrf='))?.split('=')[1]??'');
}

export const getPortfolio=()=>apiJson<Portfolio>('/v1/portfolio');
export type CapitalState={status:'UNKNOWN'}|{status:'ACTIVE';authorityId:string;availableCapitalGbp:string;
  capitalLimitGbp:string;lossLimitGbp:string;minimumAllocationScore:number;approvedAt:string;evidenceRef:string};
export type LearningState={records:{learningId:string;experimentId:string;contributionGbp:string;current:boolean}[];
  source:'MANUAL_ASSERTION'};
export const getCapital=()=>apiJson<CapitalState>('/v1/capital-authority');
export const getLearning=()=>apiJson<LearningState>('/v1/learning');
