export type RealProductInput = {
  productId: string;
  listingRef: string;
  productName: string;
  sellerName: string;
  observedAt: string;
  priceGbp: number;
  commissionRate: number;
  available: boolean;
  source: 'TIKTOK_SHOP_UI' | 'TIKTOK_CREATOR_CENTER' | 'MANUAL_VERIFIED';
};

export type RealProductRecord = RealProductInput & {
  market: 'UK';
  currency: 'GBP';
};

function nonEmpty(name:string,value:string){
 if(!value.trim()) throw new Error(`${name} is required`);
}
function finiteNonNegative(name:string,value:number){
 if(!Number.isFinite(value)||value<0) throw new Error(`${name} must be a finite non-negative number`);
}

export function ingestRealProduct(input:RealProductInput):RealProductRecord {
 nonEmpty('productId',input.productId); nonEmpty('listingRef',input.listingRef);
 nonEmpty('productName',input.productName); nonEmpty('sellerName',input.sellerName);
 if(!Number.isFinite(Date.parse(input.observedAt))) throw new Error('observedAt must be a valid timestamp');
 finiteNonNegative('priceGbp',input.priceGbp);
 if(!Number.isFinite(input.commissionRate)||input.commissionRate<0||input.commissionRate>1) throw new Error('commissionRate must be between 0 and 1');
 if(!['TIKTOK_SHOP_UI','TIKTOK_CREATOR_CENTER','MANUAL_VERIFIED'].includes(input.source)) throw new Error('unsupported product source');
 return {...input,productId:input.productId.trim(),listingRef:input.listingRef.trim(),productName:input.productName.trim(),sellerName:input.sellerName.trim(),market:'UK',currency:'GBP'};
}

export function isFreshProduct(record:RealProductRecord,nowIso:string,maxAgeHours=24):boolean {
 const now=Date.parse(nowIso), observed=Date.parse(record.observedAt);
 if(!Number.isFinite(now)||!Number.isFinite(observed)||maxAgeHours<0) throw new Error('valid time inputs required');
 return now>=observed && now-observed<=maxAgeHours*60*60*1000;
}
