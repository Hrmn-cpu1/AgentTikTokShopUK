import type { CapacitorConfig } from '@capacitor/cli';

const origin = process.env.ANDROID_APP_ORIGIN || 'https://tiktok-shop-profit-agent-uk-production.up.railway.app';
if (origin) {
  const parsed = new URL(origin);
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.search || parsed.hash ||
      parsed.pathname !== '/' || parsed.origin !== origin.replace(/\/$/, '')) {
    throw new Error('ANDROID_APP_ORIGIN must be a bare HTTPS origin with no credentials or path');
  }
}

const config: CapacitorConfig = {
  appId: 'com.tiktokshopprofitagent.app',
  appName: 'AgentTikTok Shop',
  webDir: 'dist',
  ...(origin ? {server: {url: origin, cleartext: false}} : {}),
};

export default config;
