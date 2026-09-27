import { RealityEvidenceRegistry, type RealityEvidence } from './realityEvidenceRegistry';

export const REALITY_STORAGE_KEY = 'tiktok-profit-agent:reality-evidence:v1';

export type RealityEvidenceStore = {
  load(): RealityEvidence[];
  save(items: RealityEvidence[]): void;
};

export class BrowserRealityEvidenceStore implements RealityEvidenceStore {
  constructor(private readonly storage: Pick<Storage, 'getItem' | 'setItem'>) {}

  load(): RealityEvidence[] {
    const raw = this.storage.getItem(REALITY_STORAGE_KEY);
    if (!raw) return [];
    try {
      const parsed: unknown = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed as RealityEvidence[] : [];
    } catch {
      return [];
    }
  }

  save(items: RealityEvidence[]): void {
    this.storage.setItem(REALITY_STORAGE_KEY, JSON.stringify(items));
  }
}

export function hydrateRealityRegistry(store: RealityEvidenceStore): RealityEvidenceRegistry {
  const registry = new RealityEvidenceRegistry();
  for (const item of store.load()) {
    try { registry.record(item); } catch { /* corrupt or unsafe records fail closed */ }
  }
  return registry;
}

export function persistRealityEvidence(store: RealityEvidenceStore, items: RealityEvidence[]): void {
  store.save(items.map((item) => structuredClone(item)));
}
