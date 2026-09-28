import { registerPlugin } from '@capacitor/core';

export type AndroidAuthorization = {
  state: string;
  codeVerifier: string;
  code: string;
  grantedPermissions: string;
};
export type PendingAndroidAuthorization = {available:false}|({available:true}&AndroidAuthorization);

type TikTokLoginPlugin = {
  authorize(options: {state:string;clientKey:string;redirectUri:string}): Promise<AndroidAuthorization>;
  getPendingAuthorization(): Promise<PendingAndroidAuthorization>;
  completeAuthorization(): Promise<void>;
};

export const TikTokLogin = registerPlugin<TikTokLoginPlugin>('TikTokLogin');
