package com.tiktokshopprofitagent.app;

import android.content.Intent;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.tiktok.open.sdk.auth.AuthApi;
import com.tiktok.open.sdk.auth.AuthRequest;
import com.tiktok.open.sdk.auth.AuthResponse;
import com.tiktok.open.sdk.auth.utils.PKCEUtils;
import org.json.JSONObject;

@CapacitorPlugin(name = "TikTokLogin")
public class TikTokLoginPlugin extends Plugin {
    private PluginCall authorizationCall;

    @PluginMethod
    public void authorize(PluginCall call) {
        String state = call.getString("state", "");
        String clientKey = call.getString("clientKey", "");
        String redirectUri = call.getString("redirectUri", "");
        if (state.length() < 20 || clientKey.isEmpty() || !isExpectedRedirect(redirectUri)) {
            call.reject("TikTok authorization configuration is invalid");
            return;
        }
        try {
            // Replace stale or abandoned state. A delayed response for it will not match the new state.
            SecureOAuthStateStore.clear(getContext());
            String verifier = PKCEUtils.INSTANCE.generateCodeVerifier();
            JSONObject pending = new JSONObject();
            pending.put("state", state);
            pending.put("codeVerifier", verifier);
            pending.put("redirectUri", redirectUri);
            pending.put("createdAtMillis", System.currentTimeMillis());
            pending.put("ready", false);
            SecureOAuthStateStore.write(getContext(), pending);
            authorizationCall = call;
            AuthRequest request = new AuthRequest(clientKey, "user.info.basic", redirectUri,
                verifier, false, state, null);
            boolean started = new AuthApi(getActivity()).authorize(request, AuthApi.AuthMethod.TikTokApp);
            if (!started) {
                authorizationCall = null;
                SecureOAuthStateStore.clear(getContext());
                call.reject("TikTok Login Kit could not start authorization");
            }
        } catch (Exception exception) {
            authorizationCall = null;
            SecureOAuthStateStore.clear(getContext());
            call.reject("TikTok Login Kit could not start authorization");
        }
    }

    @PluginMethod
    public void getPendingAuthorization(PluginCall call) {
        try {
            JSONObject pending = SecureOAuthStateStore.read(getContext());
            if (pending == null || !pending.optBoolean("ready", false)) {
                JSObject empty = new JSObject();
                empty.put("available", false);
                call.resolve(empty);
                return;
            }
            if (isExpired(pending)) {
                SecureOAuthStateStore.clear(getContext());
                JSObject empty = new JSObject();
                empty.put("available", false);
                call.resolve(empty);
                return;
            }
            call.resolve(toPayload(pending));
        } catch (Exception exception) {
            SecureOAuthStateStore.clear(getContext());
            call.reject("Pending TikTok authorization could not be read");
        }
    }

    @PluginMethod
    public void completeAuthorization(PluginCall call) {
        SecureOAuthStateStore.clear(getContext());
        call.resolve();
    }

    @Override
    protected void handleOnNewIntent(Intent intent) {
        handleAuthorizationIntent(intent);
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void handleOnActivityResult(int requestCode, int resultCode, Intent data) {
        handleAuthorizationIntent(data);
    }

    private void handleAuthorizationIntent(Intent intent) {
        if (intent == null) return;
        try {
            JSONObject pending = SecureOAuthStateStore.read(getContext());
            if (pending == null || pending.optBoolean("ready", false)) return;
            if (isExpired(pending)) {
                SecureOAuthStateStore.clear(getContext());
                rejectAuthorization("TikTok authorization expired; please try again");
                return;
            }
            String redirectUri = pending.optString("redirectUri", "");
            AuthResponse response = new AuthApi(getActivity()).getAuthResponseFromIntent(intent, redirectUri);
            if (response == null) return;
            String expectedState = pending.optString("state", "");
            if (response.getState() == null || !expectedState.equals(response.getState())) {
                SecureOAuthStateStore.clear(getContext());
                rejectAuthorization("TikTok authorization state did not match");
                return;
            }
            String code = response.getAuthCode();
            if (code == null || code.isEmpty()) {
                SecureOAuthStateStore.clear(getContext());
                rejectAuthorization("TikTok authorization was declined");
                return;
            }
            pending.put("authCode", code);
            pending.put("grantedPermissions", response.getGrantedPermissions());
            pending.put("ready", true);
            SecureOAuthStateStore.write(getContext(), pending);
            PluginCall call = authorizationCall;
            authorizationCall = null;
            if (call != null) call.resolve(toPayload(pending));
        } catch (Exception exception) {
            SecureOAuthStateStore.clear(getContext());
            rejectAuthorization("TikTok authorization response could not be verified");
        }
    }

    private void rejectAuthorization(String message) {
        PluginCall call = authorizationCall;
        authorizationCall = null;
        if (call != null) call.reject(message);
    }

    private boolean isExpectedRedirect(String redirectUri) {
        return "https://tiktok-shop-profit-agent-uk-production.up.railway.app/v1/tiktok/callback".equals(redirectUri);
    }

    private boolean isExpired(JSONObject pending) {
        long createdAt = pending.optLong("createdAtMillis", 0L);
        return createdAt <= 0L || System.currentTimeMillis() - createdAt > 5 * 60 * 1000L;
    }

    private JSObject toPayload(JSONObject pending) throws Exception {
        JSObject result = new JSObject();
        result.put("available", true);
        result.put("state", pending.getString("state"));
        result.put("codeVerifier", pending.getString("codeVerifier"));
        result.put("code", pending.getString("authCode"));
        result.put("grantedPermissions", pending.optString("grantedPermissions", ""));
        return result;
    }
}