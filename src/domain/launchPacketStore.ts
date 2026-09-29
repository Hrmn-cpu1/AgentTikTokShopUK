export type LaunchPacket=ReturnType<typeof import('./exp001LaunchPacket').buildLaunchPacket>;
export const LAUNCH_PACKET_STORAGE_KEY='tiktok-profit-agent:launch-packet:v1';
function validate(x:LaunchPacket):LaunchPacket{if(x.experimentId!=='EXP-001'||x.decisionId!=='DEC-001'||!x.packetId||!x.creativeId||!x.productId||!Number.isFinite(Date.parse(x.createdAt)))throw new Error('Invalid launch packet');if(x.externalPublicationId!==null)throw new Error('Unverified external publication cannot be persisted here');return Object.freeze(structuredClone(x))}
export function saveLaunchPacket(storage:Pick<Storage,'setItem'>,x:LaunchPacket){const safe=validate(x);storage.setItem(LAUNCH_PACKET_STORAGE_KEY,JSON.stringify(safe));return safe}
export function loadLaunchPacket(storage:Pick<Storage,'getItem'>):LaunchPacket|null{const raw=storage.getItem(LAUNCH_PACKET_STORAGE_KEY);if(!raw)return null;try{return validate(JSON.parse(raw) as LaunchPacket)}catch{return null}}
