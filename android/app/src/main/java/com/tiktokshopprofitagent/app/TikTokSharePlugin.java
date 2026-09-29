package com.tiktokshopprofitagent.app;

import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.util.Base64;
import androidx.core.content.FileProvider;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.JSObject;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

@CapacitorPlugin(name = "TikTokShare")
public class TikTokSharePlugin extends Plugin {
    private static final int MAX_VIDEO_BYTES = 100 * 1024 * 1024;

    @PluginMethod
    public void shareVideo(PluginCall call) {
        String encoded = call.getString("base64");
        if (encoded == null || encoded.isEmpty()) {
            call.reject("Vídeo não recebido");
            return;
        }
        final byte[] bytes;
        try {
            bytes = Base64.decode(encoded, Base64.DEFAULT);
        } catch (IllegalArgumentException error) {
            call.reject("Vídeo inválido");
            return;
        }
        if (bytes.length == 0 || bytes.length > MAX_VIDEO_BYTES) {
            call.reject("Vídeo deve ter até 100 MB");
            return;
        }

        final String sha256;
        try {
            sha256 = sha256(bytes);
        } catch (NoSuchAlgorithmException error) {
            call.reject("Não foi possível validar o vídeo");
            return;
        }

        File shareDir = new File(getContext().getCacheDir(), "share");
        if ((!shareDir.exists() && !shareDir.mkdirs()) || !shareDir.isDirectory()) {
            call.reject("Não foi possível preparar a área segura de compartilhamento");
            return;
        }
        File video = new File(shareDir, "agent-tiktok-share.mp4");
        try (FileOutputStream stream = new FileOutputStream(video, false)) {
            stream.write(bytes);
            stream.flush();
        } catch (IOException error) {
            call.reject("Não foi possível preparar o vídeo para compartilhar");
            return;
        }

        Uri contentUri = FileProvider.getUriForFile(getContext(),
                getContext().getPackageName() + ".fileprovider", video);
        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType("video/mp4");
        send.putExtra(Intent.EXTRA_STREAM, contentUri);
        send.setClipData(ClipData.newUri(getContext().getContentResolver(), "AgentTikTok video", contentUri));
        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);

        String tiktokPackage = findTikTokPackage();
        if (tiktokPackage != null) {
            send.setPackage(tiktokPackage);
            try {
                getActivity().startActivity(send);
                call.resolve(handoffResult("TIKTOK_INTENT_STARTED", sha256));
                return;
            } catch (ActivityNotFoundException ignored) {
                send.setPackage(null);
            }
        }
        try {
            getActivity().startActivity(Intent.createChooser(send, "Compartilhar vídeo"));
            call.resolve(handoffResult("SHARE_CHOOSER_OPENED", sha256));
        } catch (ActivityNotFoundException error) {
            call.reject("Nenhum aplicativo disponível para compartilhar vídeo");
        }
    }

    private JSObject handoffResult(String state, String sha256) {
        JSObject result = new JSObject();
        result.put("state", state);
        result.put("artifactSha256", sha256);
        result.put("observedAtEpochMs", System.currentTimeMillis());
        return result;
    }

    private String sha256(byte[] bytes) throws NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(bytes);
        StringBuilder value = new StringBuilder(hash.length * 2);
        for (byte item : hash) {
            value.append(String.format("%02x", item & 0xff));
        }
        return value.toString();
    }

    private String findTikTokPackage() {
        String[] packages = {"com.zhiliaoapp.musically", "com.ss.android.ugc.trill"};
        for (String packageName : packages) {
            try {
                getContext().getPackageManager().getPackageInfo(packageName, 0);
                return packageName;
            } catch (Exception ignored) {
                // Try the other official TikTok package variant.
            }
        }
        return null;
    }
}
