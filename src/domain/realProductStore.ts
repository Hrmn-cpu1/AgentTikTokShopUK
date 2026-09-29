import { ingestRealProduct, type RealProductRecord } from './realProductIntake';

export const REAL_PRODUCT_STORAGE_KEY='tiktok-profit-agent:real-product:v1';

export function saveRealProduct(storage:Pick<Storage,'setItem'>,record:RealProductRecord):void {
 storage.setItem(REAL_PRODUCT_STORAGE_KEY,JSON.stringify(record));
}

export function loadRealProduct(storage:Pick<Storage,'getItem'>):RealProductRecord|null {
 const raw=storage.getItem(REAL_PRODUCT_STORAGE_KEY);
 if(!raw) return null;
 try {
  const value=JSON.parse(raw) as RealProductRecord;
  if(value.market!=='UK'||value.currency!=='GBP') return null;
  return ingestRealProduct(value);
 } catch { return null; }
}
