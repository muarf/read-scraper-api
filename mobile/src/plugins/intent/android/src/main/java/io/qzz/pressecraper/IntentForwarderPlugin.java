package io.qzz.pressecraper;

import android.content.Intent;
import android.util.Log;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.PluginResult;

@CapacitorPlugin(name = "IntentForwarder")
public class IntentForwarderPlugin extends Plugin {
    private static final String TAG = "IntentForwarder";
    private JSObject lastSharedIntent = null;

    @Override
    public void handleOnNewIntent(Intent intent) {
        super.handleOnNewIntent(intent);
        Log.d(TAG, "handleOnNewIntent called");
        handleIntent(intent);
    }

    @Override
    public void handleOnActivityResult(int requestCode, int resultCode, Intent data) {
        super.handleOnActivityResult(requestCode, resultCode, data);
    }

    private void handleIntent(Intent intent) {
        if (intent == null) return;
        String action = intent.getAction();
        String type = intent.getType();
        Log.d(TAG, "handleIntent: action=" + action + " type=" + type);

        if (Intent.ACTION_SEND.equals(action) && type != null) {
            if ("text/plain".equals(type) || "text/html".equals(type)) {
                String sharedText = intent.getStringExtra(Intent.EXTRA_TEXT);
                if (sharedText != null) {
                    Log.d(TAG, "Forwarding sharedText: " + sharedText);
                    JSObject ret = new JSObject();
                    ret.put("type", "sharedText");
                    ret.put("data", sharedText);
                    lastSharedIntent = ret;
                    notifyListeners("intentReceived", ret);
                }
            }
        } else if (Intent.ACTION_PROCESS_TEXT.equals(action)) {
            CharSequence processedText = intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);
            if (processedText != null) {
                String text = processedText.toString();
                Log.d(TAG, "Forwarding PROCESS_TEXT: " + text);
                JSObject ret = new JSObject();
                ret.put("type", "sharedText");
                ret.put("data", text);
                lastSharedIntent = ret;
                notifyListeners("intentReceived", ret);
            }
        } else if (Intent.ACTION_VIEW.equals(action)) {
            String url = intent.getDataString();
            if (url != null) {
                Log.d(TAG, "Forwarding VIEW URL: " + url);
                JSObject ret = new JSObject();
                ret.put("type", "sharedUrl");
                ret.put("data", url);
                lastSharedIntent = ret;
                notifyListeners("intentReceived", ret);
            }
        }
    }

    @PluginMethod
    public void getLastIntent(PluginCall call) {
        if (lastSharedIntent != null) {
            call.resolve(lastSharedIntent);
        } else {
            call.resolve(new JSObject());
        }
    }
}
