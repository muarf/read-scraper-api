package io.qzz.pressecraper;

import android.content.Intent;
import android.os.Bundle;
import android.util.Log;

import com.getcapacitor.BridgeActivity;
import com.getcapacitor.PluginHandle;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONException;
import org.json.JSONObject;

public class MainActivity extends BridgeActivity {

    private static final String TAG = "PresseScraper";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleIntent(intent);
    }

    private void handleIntent(Intent intent) {
        if (intent == null) return;

        String action = intent.getAction();
        String type = intent.getType();

        Log.d(TAG, "Intent received: action=" + action + ", type=" + type);

        if (Intent.ACTION_SEND.equals(action) && type != null) {
            if ("text/plain".equals(type)) {
                String sharedText = intent.getStringExtra(Intent.EXTRA_TEXT);
                String sharedTitle = intent.getStringExtra(Intent.EXTRA_SUBJECT);
                if (sharedText != null) {
                    Log.d(TAG, "Shared text: " + sharedText);
                    // Stocker le texte partagé pour que le JS puisse le récupérer
                    getBridge().getActivity().getPreferences(MODE_PRIVATE)
                        .edit()
                        .putString("shared_text", sharedText)
                        .putString("shared_title", sharedTitle != null ? sharedTitle : "")
                        .apply();
                    // Notifier le JS via un event Capacitor
                    getBridge().triggerWindowJSEvent("sharedText", sharedText);
                }
            }
        } else if (Intent.ACTION_PROCESS_TEXT.equals(action)) {
            CharSequence processedText = intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);
            if (processedText != null) {
                String text = processedText.toString();
                Log.d(TAG, "Process text: " + text);
                getBridge().getActivity().getPreferences(MODE_PRIVATE)
                    .edit()
                    .putString("shared_text", text)
                    .putString("shared_title", "")
                    .apply();
                getBridge().triggerWindowJSEvent("sharedText", text);
            }
        } else if (Intent.ACTION_VIEW.equals(action)) {
            String url = intent.getDataString();
            if (url != null) {
                Log.d(TAG, "View URL: " + url);
                getBridge().getActivity().getPreferences(MODE_PRIVATE)
                    .edit()
                    .putString("shared_url", url)
                    .apply();
                getBridge().triggerWindowJSEvent("sharedUrl", url);
            }
        }
    }
}
