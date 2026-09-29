import {describe,expect,it} from 'vitest';
import {ingestRealProduct,isFreshProduct} from './realProductIntake';

const product={productId:'P-UK-1',listingRef:'TikTok Shop listing 123',productName:'Real Product',sellerName:'UK Seller',observedAt:'2026-09-27T17:00:00Z',priceGbp:19.99,commissionRate:.15,available:true,source:'TIKTOK_CREATOR_CENTER' as const};

describe('real product intake',()=>{
 it('normalizes a traceable UK GBP product',()=>{const r=ingestRealProduct(product);expect(r.market).toBe('UK');expect(r.currency).toBe('GBP')});
 it('requires listing provenance',()=>expect(()=>ingestRealProduct({...product,listingRef:' '})).toThrow());
 it('rejects impossible commission',()=>expect(()=>ingestRealProduct({...product,commissionRate:1.2})).toThrow());
 it('rejects negative price',()=>expect(()=>ingestRealProduct({...product,priceGbp:-1})).toThrow());
 it('preserves unavailable supply as evidence rather than hiding product',()=>expect(ingestRealProduct({...product,available:false}).available).toBe(false));
 it('distinguishes fresh from stale product evidence',()=>{const r=ingestRealProduct(product);expect(isFreshProduct(r,'2026-09-27T18:00:00Z')).toBe(true);expect(isFreshProduct(r,'2026-09-29T18:00:00Z')).toBe(false)});
});
