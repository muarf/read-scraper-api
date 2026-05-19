package io.qzz.pressecraper;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(name = "BackgroundPoll")
public class BackgroundPollPlugin extends Plugin {
    private static final String TAG = "BackgroundPoll";
    private static final String CHANNEL_ID = "background_poll";
    private ExecutorService executor;
    private Handler mainHandler;
    private Runnable pollRunnable;
    private boolean isPolling = false;

    @Override
    public void load() {
        super.load();
        executor = Executors.newSingleThreadExecutor();
        mainHandler = new Handler(Looper.getMainLooper());
        createNotificationChannel();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Article Downloads",
                NotificationManager.IMPORTANCE_DEFAULT
            );
            channel.setDescription("Notifications when articles are downloaded");
            NotificationManager mgr = (NotificationManager) getContext().getSystemService(Context.NOTIFICATION_SERVICE);
            if (mgr != null) mgr.createNotificationChannel(channel);
        }
    }

    @PluginMethod
    public void startPolling(PluginCall call) {
        String jobId = call.getString("jobId");
        String apiUrl = call.getString("apiUrl");
        String apiKey = call.getString("apiKey");

        if (jobId == null || apiUrl == null) {
            call.reject("jobId and apiUrl required");
            return;
        }

        if (isPolling) {
            call.reject("Already polling");
            return;
        }

        isPolling = true;
        Log.d(TAG, "Starting poll for job " + jobId);

        pollRunnable = new Runnable() {
            int attempts = 0;
            final int MAX_ATTEMPTS = 120; // 10 min max (5s interval)

            @Override
            public void run() {
                if (!isPolling || attempts >= MAX_ATTEMPTS) {
                    isPolling = false;
                    Log.d(TAG, "Polling stopped for job " + jobId);
                    return;
                }
                attempts++;

                try {
                    String urlStr = apiUrl + "/api/v1/job/" + jobId;
                    URL url = new URL(urlStr);
                    HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("GET");
                    conn.setConnectTimeout(5000);
                    conn.setReadTimeout(5000);
                    if (apiKey != null) {
                        conn.setRequestProperty("Authorization", "Bearer " + apiKey);
                    }

                    int code = conn.getResponseCode();
                    if (code == 200) {
                        BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                        StringBuilder sb = new StringBuilder();
                        String line;
                        while ((line = reader.readLine()) != null) sb.append(line);
                        reader.close();

                        String body = sb.toString();
                        // Parse status from JSON
                        String status = extractJsonField(body, "status");
                        String title = extractJsonField(body, "article_title");
                        String articleId = extractJsonField(body, "article_id");

                        Log.d(TAG, "Poll attempt " + attempts + ": status=" + status);

                        if ("completed".equals(status)) {
                            isPolling = false;
                            showNotification(
                                "📰 Article téléchargé",
                                title != null ? title : "Nouvel article",
                                articleId != null ? articleId : jobId
                            );
                            JSObject ret = new JSObject();
                            ret.put("status", "completed");
                            ret.put("articleId", articleId);
                            ret.put("articleTitle", title);
                            notifyListeners("pollResult", ret);
                            return;
                        } else if ("failed".equals(status)) {
                            isPolling = false;
                            String error = extractJsonField(body, "error_message");
                            showNotification("❌ Échec du téléchargement", error != null ? error : "Erreur inconnue", null);
                            JSObject ret = new JSObject();
                            ret.put("status", "failed");
                            ret.put("error", error);
                            notifyListeners("pollResult", ret);
                            return;
                        }
                    }
                    conn.disconnect();
                } catch (Exception e) {
                    Log.e(TAG, "Poll error: " + e.getMessage());
                }

                // Schedule next poll in 5 seconds
                if (isPolling) {
                    mainHandler.postDelayed(this, 5000);
                }
            }
        };

        executor.execute(pollRunnable);
        call.resolve();
    }

    @PluginMethod
    public void stopPolling(PluginCall call) {
        isPolling = false;
        if (pollRunnable != null) {
            mainHandler.removeCallbacks(pollRunnable);
        }
        call.resolve();
    }

    private void showNotification(String title, String body, String articleId) {
        Context ctx = getContext();
        NotificationManager mgr = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        if (mgr == null) return;

        // Intent to open the app
        Intent intent = ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
        if (intent != null) {
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            if (articleId != null) {
                intent.putExtra("openArticle", articleId);
            }
        }

        PendingIntent pendingIntent = PendingIntent.getActivity(
            ctx, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(ctx, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(ctx);
        }

        builder.setContentTitle(title)
               .setContentText(body)
               .setSmallIcon(android.R.drawable.ic_menu_info_details)
               .setContentIntent(pendingIntent)
               .setAutoCancel(true)
               .setPriority(Notification.PRIORITY_DEFAULT);

        mgr.notify((int) System.currentTimeMillis(), builder.build());
    }

    private static String extractJsonField(String json, String field) {
        try {
            String search = "\"" + field + "\":\"";
            int start = json.indexOf(search);
            if (start < 0) return null;
            start += search.length();
            int end = json.indexOf("\"", start);
            if (end < 0) return null;
            return json.substring(start, end);
        } catch (Exception e) {
            return null;
        }
    }
}
