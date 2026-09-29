export const EXECUTION_STORAGE_KEY='tiktok-profit-agent:execution-enabled:v1';

export function readExecutionEnabled(storage:Pick<Storage,'getItem'>):boolean {
 return storage.getItem(EXECUTION_STORAGE_KEY)==='true';
}

export function writeExecutionEnabled(storage:Pick<Storage,'setItem'>,enabled:boolean):void {
 storage.setItem(EXECUTION_STORAGE_KEY,enabled?'true':'false');
}

export function executionCutoverState(enabled:boolean){
 return Object.freeze({
  executionEnabled:enabled,
  mode:enabled?'OPERATOR_ENABLED':'SAFE_MODE',
  externalExecutionAllowed:false,
  message:enabled?'Operator enabled readiness evaluation; external effects still require policy and human approval.':'Execution disabled by default.',
 });
}
