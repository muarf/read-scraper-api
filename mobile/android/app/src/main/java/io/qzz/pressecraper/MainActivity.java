package io.qzz.pressecraper;

import android.content.Intent;
import android.os.Bundle;
import android.util.Log;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private static final String TAG = "PresseScraper";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Register custom plugins
        registerPlugin(BnfLoginPlugin.class);

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
        Log.d(TAG, "Intent: action=" + action + " type=" + type);

        // Handle notification click - open specific article
        String openArticleId = intent.getStringExtra("openArticleId");
        if (openArticleId != null && !openArticleId.isEmpty()) {
            Log.d(TAG, "Open article from notification: " + openArticleId);
            notifyJs("openArticle", openArticleId);
            return;
        }

        if (Intent.ACTION_SEND.equals(action) && type != null) {
            if ("text/plain".equals(type) || "text/html".equals(type)) {
                String sharedText = intent.getStringExtra(Intent.EXTRA_TEXT);
                String sharedTitle = intent.getStringExtra(Intent.EXTRA_SUBJECT);
                if (sharedText != null) {
                    Log.d(TAG, "SEND text: " + sharedText);
                    notifyJs("sharedText", sharedText);
                }
            }
        } else if (Intent.ACTION_PROCESS_TEXT.equals(action)) {
            CharSequence processedText = intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);
            if (processedText != null) {
                String text = processedText.toString();
                Log.d(TAG, "PROCESS_TEXT: " + text);
                notifyJs("sharedText", text);
                Intent resultIntent = new Intent();
                resultIntent.putExtra(Intent.EXTRA_PROCESS_TEXT, text);
                setResult(RESULT_OK, resultIntent);
            }
        } else if (Intent.ACTION_VIEW.equals(action)) {
            String url = intent.getDataString();
            if (url != null) {
                Log.d(TAG, "VIEW URL: " + url);
                notifyJs("sharedUrl", url);
            }
        }
    }

    private void notifyJs(String event, String data) {
        try {
            getBridge().triggerWindowJSEvent(event, data);
        } catch (Exception e) {
            Log.e(TAG, "notifyJs error: " + e.getMessage());
        }
    }
}
