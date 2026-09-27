import { RealResultIngestor, type RealResultInput, type RealResultReceipt } from './realResultIngestor';

export type PublishedLaunch = {
 packetId:string; experimentId:string; creativeId:string; externalPublicationId:string; publishedAt:string; evidenceRef:string;
};

export function bindRealPublication(packet:{
 packetId:string; experimentId:string; creativeId:string; readyForManualPublish:boolean;
}, externalPublicationId:string, publishedAt:string, evidenceRef:string):PublishedLaunch {
 if(!packet.readyForManualPublish) throw new Error('Launch packet is not approved for manual publication');
 if(!externalPublicationId.trim()||!evidenceRef.trim()) throw new Error('externalPublicationId and evidenceRef are required');
 if(!Number.isFinite(Date.parse(publishedAt))) throw new Error('publishedAt must be a valid timestamp');
 return Object.freeze({packetId:packet.packetId,experimentId:packet.experimentId,creativeId:packet.creativeId,externalPublicationId:externalPublicationId.trim(),publishedAt,evidenceRef:evidenceRef.trim()});
}

export class PublishedResultCapture {
 private readonly ingestor=new RealResultIngestor();
 constructor(private readonly publication:PublishedLaunch){}
 capture(input:Omit<RealResultInput,'experimentId'|'actionId'>):RealResultReceipt {
   return this.ingestor.ingest({...input,experimentId:this.publication.experimentId,actionId:this.publication.packetId});
 }
 reward(){return this.ingestor.rewardForExperiment(this.publication.experimentId)}
}
