package com.tiktokshopprofitagent.app;

import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.util.Base64;
import androidx.core.content.FileProvider;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;

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

        File video = new File(getContext().getCacheDir(), "agent-tiktok-share.mp4");
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
                call.resolve();
                return;
            } catch (ActivityNotFoundException ignored) {
                send.setPackage(null);
            }
        }
        try {
            getActivity().startActivity(Intent.createChooser(send, "Compartilhar vídeo"));
            call.resolve();
        } catch (ActivityNotFoundException error) {
            call.reject("Nenhum aplicativo disponível para compartilhar vídeo");
        }
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
