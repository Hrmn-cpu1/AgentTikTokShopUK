import { describe, expect, it } from 'vitest';
import { calculateConfidence, confidenceForDecision } from './confidence';

describe('confidence engine', () => {
  it('uses the frozen weighted model when evidence is complete', () => {
    const result = calculateConfidence({
      sourceReliability: 90, sampleStrength: 70, freshness: 80,
      crossSourceAgreement: 60, attributionQuality: 80,
    });
    expect(result.score).toBe(78);
    expect(result.coverage).toBe(100);
    expect(result.state).toBe('KNOWN');
    expect(confidenceForDecision(result)).toBe(78);
  });

  it('keeps unknown evidence unknown instead of converting it to zero', () => {
    const result = calculateConfidence({
      sourceReliability: null, sampleStrength: null, freshness: null,
      crossSourceAgreement: null, attributionQuality: null,
    });
    expect(result.score).toBeNull();
    expect(result.coverage).toBe(0);
    expect(result.state).toBe('UNKNOWN');
    expect(confidenceForDecision(result)).toBe(0);
  });

  it('reports partial evidence and penalizes decision confidence by coverage', () => {
    const result = calculateConfidence({
      sourceReliability: 100, sampleStrength: null, freshness: 80,
      crossSourceAgreement: null, attributionQuality: null,
    });
    expect(result.score).toBe(92);
    expect(result.coverage).toBe(50);
    expect(result.state).toBe('PARTIAL');
    expect(confidenceForDecision(result)).toBe(46);
    expect(result.missing).toContain('sampleStrength');
  });

  it('distinguishes measured zero from unknown', () => {
    const measuredZero = calculateConfidence({
      sourceReliability: 0, sampleStrength: 0, freshness: 0,
      crossSourceAgreement: 0, attributionQuality: 0,
    });
    expect(measuredZero.score).toBe(0);
    expect(measuredZero.state).toBe('KNOWN');
    expect(measuredZero.coverage).toBe(100);
  });

  it('rejects out-of-range evidence values', () => {
    expect(() => calculateConfidence({
      sourceReliability: 101, sampleStrength: 50, freshness: 50,
      crossSourceAgreement: 50, attributionQuality: 50,
    })).toThrow();
  });
});
