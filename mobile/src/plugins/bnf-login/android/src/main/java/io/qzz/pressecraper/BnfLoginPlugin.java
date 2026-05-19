package io.qzz.pressecraper;

import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

@CapacitorPlugin(name = "BnfLogin")
public class BnfLoginPlugin extends Plugin {

    private static final String TAG = "BnfLoginPlugin";
    private static final String BNF_AUTH_URL = "https://bnf.idm.oclc.org/login?url=https://nouveau.europresse.com/access/ip/default.aspx?un=D000067U_1";
    private static final String EUROPRESSE_DOMAIN = "nouveau-europresse-com.bnf.idm.oclc.org";

    private WebView webView;
    private PluginCall pendingCall;
    private Handler timeoutHandler;
    private Runnable timeoutRunnable;

    @PluginMethod()
    public void login(PluginCall call) {
        String username = call.getString("username", "");
        String password = call.getString("password", "");

        if (username.isEmpty() || password.isEmpty()) {
            JSObject result = new JSObject();
            result.put("success", false);
            result.put("error", "Username and password required");
            call.resolve(result);
            return;
        }

        this.pendingCall = call;

        // Set timeout (60 seconds)
        timeoutHandler = new Handler(Looper.getMainLooper());
        timeoutRunnable = () -> {
            if (pendingCall != null) {
                cleanup();
                JSObject result = new JSObject();
                result.put("success", false);
                result.put("error", "Login timeout");
                pendingCall.resolve(result);
                pendingCall = null;
            }
        };
        timeoutHandler.postDelayed(timeoutRunnable, 60000);

        new Handler(Looper.getMainLooper()).post(() -> {
            try {
                performLogin(username, password);
            } catch (Exception e) {
                Log.e(TAG, "Login error", e);
                cleanup();
                JSObject result = new JSObject();
                result.put("success", false);
                result.put("error", e.getMessage());
                call.resolve(result);
            }
        });
    }

    private void performLogin(String username, String password) {
        // Clean up any existing WebView
        if (webView != null) {
            webView.destroy();
            webView = null;
        }

        webView = new WebView(getContext());
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setLoadWithOverviewMode(true);
        webView.getSettings().setUseWideViewPort(true);

        // Enable cookies
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        // Escape credentials for JS injection
        String safeUsername = escapeJs(username);
        String safePassword = escapeJs(password);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                Log.d(TAG, "Page finished: " + url);

                // Check if redirected to Europresse (login succeeded)
                if (url.contains(EUROPRESSE_DOMAIN) && !url.contains("login")) {
                    handleLoginSuccess(url);
                    return;
                }

                // Check for login errors
                view.evaluateJavascript(
                    "(function() {" +
                    "  var errors = document.querySelectorAll('.erreur, .error, [class*=\"error\"], .alert-danger, #error');" +
                    "  for (var i = 0; i < errors.length; i++) {" +
                    "    var t = errors[i].textContent.trim();" +
                    "    if (t && errors[i].offsetParent !== null) return t;" +
                    "  }" +
                    "  return null;" +
                    "})()",
                    errorResult -> {
                        if (errorResult != null && !errorResult.equals("null") && !errorResult.isEmpty()) {
                            String error = errorResult.replace("\"", "").trim();
                            Log.w(TAG, "Login error: " + error);
                            handleLoginFailure(error);
                            return;
                        }
                    }
                );

                // If on login page, auto-fill and submit
                if (url.contains("bnf.idm.oclc.org") || url.contains("login") || url.contains("idm.oclc.org")) {
                    String jsCode =
                        "(function() {" +
                        "  var u = document.querySelector(\"input[type='text'], input[id*='user'], input[name*='user'], input[name='username'], input[name='j_username']\");" +
                        "  var p = document.querySelector(\"input[type='password'], input[name='j_password']\");" +
                        "  if (u && p) {" +
                        "    u.value = '" + safeUsername + "';" +
                        "    u.dispatchEvent(new Event('input', {bubbles: true}));" +
                        "    u.dispatchEvent(new Event('change', {bubbles: true}));" +
                        "    p.value = '" + safePassword + "';" +
                        "    p.dispatchEvent(new Event('input', {bubbles: true}));" +
                        "    p.dispatchEvent(new Event('change', {bubbles: true}));" +
                        "    var btn = document.querySelector(\"input[type='submit'], button[type='submit'], button.submit, .btn-primary\");" +
                        "    if (btn) { btn.click(); return 'submitted'; }" +
                        "    var form = document.querySelector('form');" +
                        "    if (form) { form.submit(); return 'submitted'; }" +
                        "    return 'no_submit';" +
                        "  }" +
                        "  return 'no_fields';" +
                        "})()";

                    view.evaluateJavascript(jsCode, fillResult -> {
                        Log.d(TAG, "Form fill: " + fillResult);
                    });
                }
            }
        });

        webView.loadUrl(BNF_AUTH_URL);
    }

    private void handleLoginSuccess(String url) {
        if (timeoutHandler != null && timeoutRunnable != null) {
            timeoutHandler.removeCallbacks(timeoutRunnable);
        }

        CookieManager cookieManager = CookieManager.getInstance();
        String cookiesStr = cookieManager.getCookie("https://" + EUROPRESSE_DOMAIN);
        Log.d(TAG, "Cookies: " + (cookiesStr != null ? cookiesStr.substring(0, Math.min(200, cookiesStr.length())) + "..." : "null"));

        JSObject result = new JSObject();

        if (cookiesStr != null && !cookiesStr.isEmpty()) {
            try {
                JSONArray cookieArray = new JSONArray();
                String[] pairs = cookiesStr.split(";");
                for (String pair : pairs) {
                    String[] parts = pair.trim().split("=", 2);
                    if (parts.length == 2) {
                        JSONObject cookie = new JSONObject();
                        cookie.put("name", parts[0].trim());
                        cookie.put("value", parts[1].trim());
                        cookie.put("domain", EUROPRESSE_DOMAIN);
                        cookie.put("path", "/");
                        cookieArray.put(cookie);
                    }
                }
                result.put("success", true);
                result.put("cookies", cookieArray);
                result.put("cookieHeader", cookiesStr);
            } catch (JSONException e) {
                result.put("success", false);
                result.put("error", "Cookie parsing error: " + e.getMessage());
            }
        } else {
            result.put("success", false);
            result.put("error", "No cookies found after login");
        }

        cleanup();

        if (pendingCall != null) {
            pendingCall.resolve(result);
            pendingCall = null;
        }
    }

    private void handleLoginFailure(String error) {
        if (timeoutHandler != null && timeoutRunnable != null) {
            timeoutHandler.removeCallbacks(timeoutRunnable);
        }

        cleanup();

        if (pendingCall != null) {
            JSObject result = new JSObject();
            result.put("success", false);
            result.put("error", error);
            pendingCall.resolve(result);
            pendingCall = null;
        }
    }

    private void cleanup() {
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
            webView = null;
        }
    }

    private String escapeJs(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("'", "\\'").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r");
    }

    @PluginMethod()
    public void httpRequest(PluginCall call) {
        String urlStr = call.getString("url", "");
        String method = call.getString("method", "GET");
        JSObject bodyObj = call.getObject("body", null);
        JSObject headersObj = call.getObject("headers", null);

        if (urlStr.isEmpty()) {
            JSObject result = new JSObject();
            result.put("error", "URL required");
            call.resolve(result);
            return;
        }

        // Run on background thread
        new Thread(() -> {
            try {
                URL url = new URL(urlStr);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod(method.toUpperCase());
                conn.setConnectTimeout(30000);
                conn.setReadTimeout(30000);

                // Set headers
                if (headersObj != null) {
                    java.util.Iterator<String> keys = headersObj.keys();
                    while (keys.hasNext()) {
                        String key = keys.next();
                        conn.setRequestProperty(key, headersObj.getString(key));
                    }
                }

                // Set body for POST/PUT
                String bodyStr = call.getString("body", null);
                if (bodyStr != null && (method.equalsIgnoreCase("POST") || method.equalsIgnoreCase("PUT"))) {
                    conn.setDoOutput(true);
                    OutputStream os = conn.getOutputStream();
                    os.write(bodyStr.getBytes("UTF-8"));
                    os.flush();
                    os.close();
                }

                int status = conn.getResponseCode();

                // Read response
                BufferedReader br;
                if (status >= 400) {
                    br = new BufferedReader(new InputStreamReader(conn.getErrorStream()));
                } else {
                    br = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                }
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = br.readLine()) != null) {
                    sb.append(line);
                }
                br.close();

                JSObject result = new JSObject();
                result.put("status", status);
                result.put("data", sb.toString());
                call.resolve(result);

            } catch (Exception e) {
                Log.e(TAG, "httpRequest error", e);
                JSObject result = new JSObject();
                result.put("error", e.getMessage());
                call.resolve(result);
            }
        }).start();
    }

    @PluginMethod()
    public void downloadFile(PluginCall call) {
        String urlStr = call.getString("url", "");
        String filename = call.getString("filename", "download.pdf");

        if (urlStr.isEmpty()) {
            JSObject result = new JSObject();
            result.put("error", "URL required");
            call.resolve(result);
            return;
        }

        new Thread(() -> {
            try {
                URL url = new URL(urlStr);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(30000);
                conn.setReadTimeout(60000);

                int status = conn.getResponseCode();
                if (status != 200) {
                    JSObject result = new JSObject();
                    result.put("error", "HTTP " + status);
                    call.resolve(result);
                    return;
                }

                // Sauvegarder dans le dossier Downloads de l'app
                java.io.File downloadsDir = android.os.Environment.getExternalStoragePublicDirectory(
                    android.os.Environment.DIRECTORY_DOCUMENTS);
                if (!downloadsDir.exists()) downloadsDir.mkdirs();
                java.io.File outFile = new java.io.File(downloadsDir, filename);

                java.io.InputStream is = conn.getInputStream();
                java.io.FileOutputStream fos = new java.io.FileOutputStream(outFile);
                byte[] buffer = new byte[8192];
                int len;
                while ((len = is.read(buffer)) != -1) {
                    fos.write(buffer, 0, len);
                }
                fos.close();
                is.close();

                JSObject result = new JSObject();
                result.put("success", true);
                result.put("path", outFile.getAbsolutePath());
                call.resolve(result);

            } catch (Exception e) {
                Log.e(TAG, "downloadFile error", e);
                JSObject result = new JSObject();
                result.put("error", e.getMessage());
                call.resolve(result);
            }
        }).start();
    }

    @PluginMethod()
    public void showNotification(PluginCall call) {
        String title = call.getString("title", "Presse Scraper");
        String body = call.getString("body", "");
        String articleId = call.getString("articleId", "");

        try {
            android.app.NotificationManager notificationManager =
                (android.app.NotificationManager) getContext().getSystemService(android.content.Context.NOTIFICATION_SERVICE);

            // Create notification channel for Android O+
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                android.app.NotificationChannel channel = new android.app.NotificationChannel(
                    "presse_scraper", "Articles", android.app.NotificationManager.IMPORTANCE_DEFAULT);
                channel.setDescription("Notifications d'articles téléchargés");
                notificationManager.createNotificationChannel(channel);
            }

            // Build intent to open the app
            android.content.Intent intent = new android.content.Intent(getContext(), MainActivity.class);
            intent.setFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK | android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP);
            if (articleId != null && !articleId.isEmpty()) {
                intent.putExtra("openArticleId", articleId);
            }

            android.app.PendingIntent pendingIntent = android.app.PendingIntent.getActivity(
                getContext(), 0, intent,
                android.app.PendingIntent.FLAG_UPDATE_CURRENT | android.app.PendingIntent.FLAG_IMMUTABLE);

            // Build notification
            androidx.core.app.NotificationCompat.Builder builder =
                new androidx.core.app.NotificationCompat.Builder(getContext(), "presse_scraper")
                    .setSmallIcon(android.R.drawable.ic_menu_info_details)
                    .setContentTitle(title)
                    .setContentText(body)
                    .setPriority(androidx.core.app.NotificationCompat.PRIORITY_DEFAULT)
                    .setContentIntent(pendingIntent)
                    .setAutoCancel(true);

            notificationManager.notify((int) System.currentTimeMillis(), builder.build());

            JSObject result = new JSObject();
            result.put("success", true);
            call.resolve(result);
        } catch (Exception e) {
            Log.e(TAG, "showNotification error", e);
            JSObject result = new JSObject();
            result.put("error", e.getMessage());
            call.resolve(result);
        }
    }

    @PluginMethod()
    public void requestNotificationPermission(PluginCall call) {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            // Android 13+ needs runtime permission
            if (getContext().checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                    != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                // Request permission via activity
                getActivity().requestPermissions(
                    new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 1001);
            }
        }
        JSObject result = new JSObject();
        result.put("success", true);
        call.resolve(result);
    }
}
