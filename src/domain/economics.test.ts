import { describe, expect, it } from 'vitest';
import { calculateEconomics, realizedContribution } from './economics';

describe('economics engine', () => {
  it('calculates commission and risk-adjusted expected realized profit', () => {
    const result = calculateEconomics({
      expectedOrders: 10, paidPrice: 24.99, commissionRate: 0.18,
      settlementProbability: 0.8, experimentCost: 8,
      capitalRequired: 8, timeToCashDays: 4, experimentShots: 2, experimentHours: 3,
    });
    expect(result.commissionPerOrder).toBe(4.5);
    expect(result.expectedCommission).toBe(44.98);
    expect(result.expectedSettledCommission).toBe(35.99);
    expect(result.expectedRealizedProfit).toBe(27.99);
    expect(result.cashVelocity).toBe(0.87);
    expect(result.expectedGbpPerShot).toBe(13.99);
    expect(result.expectedGbpPerHour).toBe(9.33);
  });

  it('allows negative expected profit instead of hiding a losing experiment', () => {
    expect(calculateEconomics({
      expectedOrders: 1, paidPrice: 10, commissionRate: 0.1,
      settlementProbability: 0.5, experimentCost: 8,
      capitalRequired: 8, timeToCashDays: 5,
    }).expectedRealizedProfit).toBe(-7.5);
  });

  it('uses settled commission, not orders, for realized contribution', () => {
    expect(realizedContribution(20, 8)).toBe(12);
    expect(realizedContribution(0, 8)).toBe(-8);
  });

  it('rejects invalid probabilities and negative money inputs', () => {
    expect(() => calculateEconomics({
      expectedOrders: 1, paidPrice: 10, commissionRate: 1.2,
      settlementProbability: 1, experimentCost: 0, capitalRequired: 0, timeToCashDays: 1,
    })).toThrow();
    expect(() => realizedContribution(-1, 0)).toThrow();
  });
});
