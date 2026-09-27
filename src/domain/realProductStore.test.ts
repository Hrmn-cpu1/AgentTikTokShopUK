import {describe,expect,it} from 'vitest';
import {loadRealProduct,saveRealProduct,REAL_PRODUCT_STORAGE_KEY} from './realProductStore';
import type {RealProductRecord} from './realProductIntake';

const product:RealProductRecord={productId:'P1',listingRef:'listing-1',productName:'Real Product',sellerName:'Seller',observedAt:'2026-09-27T17:00:00Z',priceGbp:20,commissionRate:.2,available:true,source:'TIKTOK_CREATOR_CENTER',market:'UK',currency:'GBP'};
describe('real product store',()=>{
 it('preserves original product provenance',()=>{let raw:string|null=null;saveRealProduct({setItem:(k,v)=>{expect(k).toBe(REAL_PRODUCT_STORAGE_KEY);raw=v}},product);const loaded=loadRealProduct({getItem:()=>raw});expect(loaded).toEqual(product)});
 it('returns null when no real product exists',()=>expect(loadRealProduct({getItem:()=>null})).toBeNull());
 it('fails closed on corrupt storage',()=>expect(loadRealProduct({getItem:()=>'{bad'})).toBeNull());
 it('rejects non-UK persisted records',()=>expect(loadRealProduct({getItem:()=>JSON.stringify({...product,market:'BR'})})).toBeNull());
});
