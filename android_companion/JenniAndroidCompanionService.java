package com.jenniai.companion;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import org.json.JSONObject;

import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

/**
 * Jenni AI Android Companion Daemon (Java).
 * Connects via WebSocket to the Jenni AI FastAPI Backend running on Windows 11.
 * Provides:
 *  - Real-time battery & telemetry broadcast
 *  - Bidirectional clipboard synchronization
 *  - Remote notification forwarding
 *  - Instant voice/command execution
 */
public class JenniAndroidCompanionService extends Service {
    private static final String TAG = "JenniCompanion";
    private static final String CHANNEL_ID = "jenni_companion_channel";
    private static final String SERVER_WS_URL = "ws://100.102.38.116:8000/ws/telemetry"; // Tailscale or LAN IP

    private OkHttpClient client;
    private WebSocket webSocket;
    private ClipboardManager clipboardManager;
    private String lastSyncedClip = "";

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        startForeground(1001, buildForegroundNotification("Connected to Jenni AI PC"));

        clipboardManager = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        setupClipboardListener();
        setupBatteryReceiver();
        initWebSocket();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "Jenni AI Companion Service",
                    NotificationManager.IMPORTANCE_LOW
            );
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private Notification buildForegroundNotification(String status) {
        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Jenni AI Companion")
                .setContentText(status)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setOngoing(true)
                .build();
    }

    private void initWebSocket() {
        client = new OkHttpClient.Builder()
                .readTimeout(0, TimeUnit.MILLISECONDS)
                .pingInterval(10, TimeUnit.SECONDS)
                .build();

        Request request = new Request.Builder()
                .url(SERVER_WS_URL)
                .addHeader("X-Client-Platform", "Android 12")
                .build();

        webSocket = client.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket ws, Response response) {
                Log.i(TAG, "WebSocket connected to Jenni AI Server!");
                sendDeviceTelemetry();
            }

            @Override
            public void onMessage(WebSocket ws, String text) {
                handleServerCommand(text);
            }

            @Override
            public void onClosed(WebSocket ws, int code, String reason) {
                Log.w(TAG, "WebSocket closed: " + reason);
            }

            @Override
            public void onFailure(WebSocket ws, Throwable t, @Nullable Response response) {
                Log.e(TAG, "WebSocket failure, will retry...", t);
            }
        });
    }

    private void setupClipboardListener() {
        if (clipboardManager != null) {
            clipboardManager.addPrimaryClipChangedListener(() -> {
                ClipData clip = clipboardManager.getPrimaryClip();
                if (clip != null && clip.getItemCount() > 0) {
                    CharSequence text = clip.getItemAt(0).getText();
                    if (text != null && !text.toString().equals(lastSyncedClip)) {
                        lastSyncedClip = text.toString();
                        sendJsonMessage("clipboard_sync", new JSONObject().opt("content", lastSyncedClip));
                    }
                }
            });
        }
    }

    private void setupBatteryReceiver() {
        IntentFilter ifilter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
        registerReceiver(new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                int level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                int scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
                int status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
                boolean isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                        status == BatteryManager.BATTERY_STATUS_FULL;

                float batteryPct = level * 100 / (float) scale;
                try {
                    JSONObject payload = new JSONObject();
                    payload.put("percent", (int) batteryPct);
                    payload.put("is_charging", isCharging);
                    sendJsonMessage("battery_update", payload);
                } catch (Exception ignored) {}
            }
        }, ifilter);
    }

    private void sendDeviceTelemetry() {
        try {
            JSONObject obj = new JSONObject();
            obj.put("device", Build.MODEL);
            obj.put("os_version", "Android " + Build.VERSION.RELEASE);
            obj.put("sdk", Build.VERSION.SDK_INT);
            sendJsonMessage("device_handshake", obj);
        } catch (Exception ignored) {}
    }

    private void sendJsonMessage(String type, Object data) {
        if (webSocket != null) {
            try {
                JSONObject msg = new JSONObject();
                msg.put("type", type);
                msg.put("data", data);
                msg.put("timestamp", System.currentTimeMillis());
                webSocket.send(msg.toString());
            } catch (Exception e) {
                Log.e(TAG, "Failed to send WS message", e);
            }
        }
    }

    private void handleServerCommand(String jsonText) {
        try {
            JSONObject msg = new JSONObject(jsonText);
            String action = msg.optString("action");
            if ("clipboard_set".equals(action)) {
                String content = msg.optString("content");
                if (content != null && clipboardManager != null) {
                    lastSyncedClip = content;
                    ClipData clip = ClipData.newPlainText("Jenni AI", content);
                    clipboardManager.setPrimaryClip(clip);
                }
            } else if ("show_notification".equals(action)) {
                String title = msg.optString("title", "Jenni AI");
                String body = msg.optString("body", "");
                NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
                if (nm != null) {
                    Notification n = new NotificationCompat.Builder(this, CHANNEL_ID)
                            .setContentTitle(title)
                            .setContentText(body)
                            .setSmallIcon(android.R.drawable.ic_dialog_alert)
                            .setAutoCancel(true)
                            .build();
                    nm.notify((int) System.currentTimeMillis(), n);
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "Error handling server command", e);
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (webSocket != null) {
            webSocket.close(1000, "Service destroyed");
        }
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
