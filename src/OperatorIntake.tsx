import { useState, type FormEvent } from 'react';
import { apiJson, operatorCsrf } from './apiClient';

type Field = {key:string; label:string; kind?:'money'|'number'|'date'|'choice'|'paragraph'; optional?:boolean; choices?:string[]};
type Step = {name:string; path:string; fields:Field[]};
const id=(key:string,label:string):Field=>({key,label});
const evidence=id('evidence_ref','Where did you observe this? Evidence reference');
const experiment=id('experiment_id','Experiment ID');
const product=id('product_id','Product ID');
const creative=id('creative_id','Creative ID');
const date:Field={key:'observed_at',label:'Observation time',kind:'date'};
const money=(key:string,label:string):Field=>({key,label,kind:'money'});

const steps:Step[]=[
  {name:'1 · Capital limits',path:'capital-authority',fields:[id('authority_id','Authority ID'),money('available_capital_gbp','Available capital £'),
    money('capital_limit_gbp','Limit per experiment £'),money('loss_limit_gbp','Maximum loss £'),{key:'minimum_allocation_score',label:'Minimum allocation score 0–100',kind:'number'},evidence]},
  {name:'2 · UK product',path:'products',fields:[product,id('listing_ref','TikTok Shop listing reference'),evidence,date]},
  {name:'3 · Opportunity evidence',path:'opportunities',fields:[id('opportunity_id','Opportunity ID'),product,
    money('capital_required_gbp','Capital required £'),money('maximum_loss_gbp','Maximum possible loss £'),
    {key:'allocation_score',label:'Allocation score 0–100',kind:'number'},evidence,date]},
  {name:'4 · Freeze experiment',path:'experiments',fields:[experiment,id('decision_id','Decision ID'),product,creative,
    id('publication_action_id','Publication action ID'),id('opportunity_id','Opportunity ID'),
    id('authority_evidence_ref','Decision authority evidence reference')]},
  {name:'5 · Product claim',path:'product-claims',fields:[id('claim_id','Claim ID'),product,
    id('text','Exact factual claim'),{key:'state',label:'Evidence state',kind:'choice',choices:['UNKNOWN','SUPPORTED','VERIFIED','BLOCKED']},
    {...evidence,optional:true}]},
  {name:'6 · Creative',path:'creatives',fields:[creative,experiment,{key:'content',label:'Creative content or immutable script',kind:'paragraph'},
    id('claim_ids','Claim IDs, separated by commas'),evidence]},
  {name:'7 · Human approval',path:'creative-approvals',fields:[id('approval_id','Approval ID'),experiment,creative,evidence]},
  {name:'8 · Manual launch intent',path:'launch-intents',fields:[id('packet_id','Launch packet ID'),experiment,id('approval_id','Approval ID')]},
  {name:'9 · Observed publication / commerce',path:'events',fields:[experiment,id('action_id','Publication action ID'),
    {key:'event_type',label:'Observed event',kind:'choice',choices:['PUBLISHED','ORDER_CREATED','DELIVERED','COMMISSION_SETTLED','REFUNDED']},
    id('external_event_id','External video / order / event ID'),{...id('parent_external_event_id','Related video, order or settlement ID'),optional:true},
    {...money('amount_gbp','Observed GBP amount'),optional:true},
    id('evidence_ref','Proof reference for this event'),{key:'occurred_at',label:'When it happened',kind:'date'}]},
  {name:'10 · Observed cost',path:'costs',fields:[experiment,money('amount_gbp','Observed cost £'),evidence]},
  {name:'11 · Additional cost',path:'cost-adjustments',fields:[id('adjustment_id','Adjustment ID'),experiment,
    money('amount_gbp','Additional cost £'),evidence]},
  {name:'12 · Economic learning',path:'learning',fields:[id('learning_id','Learning ID'),experiment]},
];

export default function OperatorIntake({onRecorded}:{onRecorded:()=>void}){
  const [stepIndex,setStepIndex]=useState(0);
  const [draft,setDraft]=useState<Record<string,string>>({});
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const step=steps[stepIndex];
  const submit=async(e:FormEvent)=>{
    e.preventDefault();setMessage('');setBusy(true);
    const payload:Record<string,unknown>={};
    for(const field of step.fields){
      const value=(draft[field.key]??'').trim();
      if(!value && field.optional)continue;
      payload[field.key]=field.kind==='date'?new Date(value).toISOString():field.key==='claim_ids'?
        value.split(',').map(x=>x.trim()).filter(Boolean):field.kind==='number'?Number(value):value;
    }
    if(step.path==='events')payload.source='MANUAL_VERIFIED';
    try{
      const result=await apiJson<Record<string,unknown>>('/v1/'+step.path,{method:'POST',
        headers:{'Content-Type':'application/json','X-CSRF-Token':operatorCsrf()},body:JSON.stringify(payload)});
      setMessage(`Recorded on server · ${JSON.stringify(result)}`);
      onRecorded();
    }catch(error){setMessage(error instanceof Error?error.message:'Server rejected this observation')}
    finally{setBusy(false)}
  };
  return <div className="operator-intake"><h2>Manual UK experiment</h2>
    <p>Only record facts you personally observed. The server checks limits, claims and approval. A launch packet does not publish anything.</p>
    <label>Next operation<select value={stepIndex} onChange={e=>{setStepIndex(Number(e.target.value));setDraft({});setMessage('')}}>
      {steps.map((item,index)=><option key={item.path} value={index}>{item.name}</option>)}</select></label>
    <form onSubmit={e=>{void submit(e)}}>{step.fields.map(field=><label key={field.key}>{field.label}
      {field.kind==='choice'?<select required value={draft[field.key]??''} onChange={e=>setDraft({...draft,[field.key]:e.target.value})}>
        <option value="">Choose observed state</option>{field.choices?.map(choice=><option key={choice}>{choice}</option>)}</select>:
      field.kind==='paragraph'?<textarea required value={draft[field.key]??''} onChange={e=>setDraft({...draft,[field.key]:e.target.value})}/>:
      <input required={!field.optional} type={field.kind==='date'?'datetime-local':'text'}
        inputMode={field.kind==='money'||field.kind==='number'?'decimal':undefined}
        value={draft[field.key]??''} onChange={e=>setDraft({...draft,[field.key]:e.target.value})}/> }</label>)}
      <button disabled={busy}>{busy?'Checking server…':'Record with server'}</button></form>
    {message&&<p role="status" className="connection-warning">{message}</p>}
  </div>;
}
