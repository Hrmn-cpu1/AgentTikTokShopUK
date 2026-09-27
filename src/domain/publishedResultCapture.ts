import { RealResultIngestor, type RealResultInput, type RealResultReceipt } from './realResultIngestor';
import type { BusinessTruthStore } from './businessTruthStore';

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
 private readonly ingestor:RealResultIngestor;
 readonly publicationReceipt:RealResultReceipt;
 constructor(private readonly publication:PublishedLaunch,store?:BusinessTruthStore){
   this.ingestor=new RealResultIngestor(store);
   this.publicationReceipt=this.ingestor.ingest({source:'MANUAL_VERIFIED',externalEventId:publication.externalPublicationId,experimentId:publication.experimentId,actionId:publication.packetId,type:'PUBLISHED',occurredAt:publication.publishedAt,amountGbp:null,evidenceRef:publication.evidenceRef});
 }
 capture(input:Omit<RealResultInput,'experimentId'|'actionId'>):RealResultReceipt {
   return this.ingestor.ingest({...input,experimentId:this.publication.experimentId,actionId:this.publication.packetId});
 }
 reward(){return this.ingestor.rewardForExperiment(this.publication.experimentId)}
}
