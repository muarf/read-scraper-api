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
}
