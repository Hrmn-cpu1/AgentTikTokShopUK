export type EconomicsInput = {
  expectedOrders: number;
  paidPrice: number;
  commissionRate: number;
  settlementProbability: number;
  experimentCost: number;
  capitalRequired: number;
  timeToCashDays: number;
  experimentShots?: number;
  experimentHours?: number;
};

export type EconomicsResult = {
  commissionPerOrder: number;
  expectedCommission: number;
  expectedSettledCommission: number;
  expectedRealizedProfit: number;
  cashVelocity: number;
  expectedGbpPerShot: number | null;
  expectedGbpPerHour: number | null;
};

const EPSILON = 0.01;
const money = (value: number) => Math.round((value + Number.EPSILON) * 100) / 100;

function assertFiniteNonNegative(name: string, value: number) {
  if (!Number.isFinite(value) || value < 0) throw new Error(`${name} must be a finite non-negative number`);
}
function assertProbability(name: string, value: number) {
  if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error(`${name} must be between 0 and 1`);
}

export function calculateEconomics(input: EconomicsInput): EconomicsResult {
  assertFiniteNonNegative('expectedOrders', input.expectedOrders);
  assertFiniteNonNegative('paidPrice', input.paidPrice);
  assertProbability('commissionRate', input.commissionRate);
  assertProbability('settlementProbability', input.settlementProbability);
  assertFiniteNonNegative('experimentCost', input.experimentCost);
  assertFiniteNonNegative('capitalRequired', input.capitalRequired);
  assertFiniteNonNegative('timeToCashDays', input.timeToCashDays);
  if (input.experimentShots !== undefined) assertFiniteNonNegative('experimentShots', input.experimentShots);
  if (input.experimentHours !== undefined) assertFiniteNonNegative('experimentHours', input.experimentHours);

  const commissionPerOrder = input.paidPrice * input.commissionRate;
  const expectedCommission = input.expectedOrders * commissionPerOrder;
  const expectedSettledCommission = expectedCommission * input.settlementProbability;
  const expectedRealizedProfit = expectedSettledCommission - input.experimentCost;
  const denominator = Math.max(input.capitalRequired * input.timeToCashDays, EPSILON);

  return {
    commissionPerOrder: money(commissionPerOrder),
    expectedCommission: money(expectedCommission),
    expectedSettledCommission: money(expectedSettledCommission),
    expectedRealizedProfit: money(expectedRealizedProfit),
    cashVelocity: money(expectedRealizedProfit / denominator),
    expectedGbpPerShot: input.experimentShots && input.experimentShots > 0 ? money(expectedRealizedProfit / input.experimentShots) : null,
    expectedGbpPerHour: input.experimentHours && input.experimentHours > 0 ? money(expectedRealizedProfit / input.experimentHours) : null,
  };
}

export function realizedContribution(settledCommission: number, experimentCosts: number): number {
  assertFiniteNonNegative('settledCommission', settledCommission);
  assertFiniteNonNegative('experimentCosts', experimentCosts);
  return money(settledCommission - experimentCosts);
}
