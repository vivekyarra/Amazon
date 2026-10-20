package dev.doneirl.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Native Fire OS shell; device validation is tracked separately from browser tests.
 * All four views consume the authenticated server ledger. No embedded device tokens,
 * JavaScript bridge, cleartext release transport, or third-party entertainment locks.
 */
public final class MainActivity extends Activity {
    private WebView web;
    private String base;
    private SharedPreferences prefs;
    private TextView status;
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        prefs = getSharedPreferences("connection", MODE_PRIVATE);
        base = prefs.getString("base", "");
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackgroundColor(Color.rgb(17,31,35));
        LinearLayout bar = new LinearLayout(this);
        bar.setPadding(20, 8, 20, 8);
        String[][] views = {{"Ledger", "overview"}, {"Incident review", "incidents"}, {"Evidence packet", "incidents"}, {"Reality-Lock", "studio"}};
        for (String[] view : views) {
            Button button = new Button(this);
            button.setText(view[0]);
            button.setOnClickListener(v -> load(view[1]));
            bar.addView(button, new LinearLayout.LayoutParams(0, 60, 1));
        }
        Button connect = new Button(this);
        connect.setText("Connection");
        connect.setOnClickListener(v -> connection());
        bar.addView(connect);
        layout.addView(bar);
        status = new TextView(this);
        status.setTextColor(Color.rgb(188,246,223));
        status.setText("SYNTHETIC DEMO · in-app gate only · Fire OS runtime proof pending");
        status.setPadding(25, 8, 25, 8);
        layout.addView(status);
        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setMediaPlaybackRequiresUserGesture(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
                Uri u = request.getUrl();
                Uri expected = Uri.parse(base);
                return !(u.getScheme().equals(expected.getScheme()) && u.getAuthority().equals(expected.getAuthority()));
            }
            @Override public void onReceivedError(WebView v, android.webkit.WebResourceRequest request, android.webkit.WebResourceError error) {
                if (request.isForMainFrame()) status.setText("Connection unavailable. Use Connection to retry; no promise was verified.");
            }
        });
        layout.addView(web, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(layout);
        if (base.isEmpty()) connection(); else load("overview");
    }
    private void load(String page) {
        if (base.isEmpty()) { connection(); return; }
        web.loadUrl(base + "/?tv=1&page=" + page);
        web.requestFocus();
    }
    private void connection() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setHint("https://your-private-backend.example");
        input.setText(base);
        new AlertDialog.Builder(this).setTitle("Your DONE/IRL backend").setMessage("Use a private HTTPS service. Debug builds also allow a local development HTTP server. Sign in with owner or judge credentials on the next screen.")
            .setView(input).setPositiveButton("Connect", (dialog, which) -> {
                String value = input.getText().toString().trim().replaceAll("/+$", "");
                Uri uri = Uri.parse(value);
                boolean scheme = "https".equals(uri.getScheme()) || (BuildConfig.DEBUG && "http".equals(uri.getScheme()));
                if (!scheme || uri.getHost() == null || uri.getUserInfo() != null || (uri.getPath()!=null && !uri.getPath().isEmpty())) {
                    status.setText("Enter a valid origin URL. Release builds require HTTPS."); return;
                }
                base = value;
                prefs.edit().putString("base", base).apply();
                load("overview");
            }).setNegativeButton("Cancel", null).show();
    }
    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getKeyCode() == KeyEvent.KEYCODE_BACK && event.getAction() == KeyEvent.ACTION_UP) {
            if (web.canGoBack()) web.goBack(); else load("overview");
            return true;
        }
        return super.dispatchKeyEvent(event);
    }
    @Override protected void onPause() { web.onPause(); CookieManager.getInstance().flush(); super.onPause(); }
    @Override protected void onResume() { super.onResume(); web.onResume(); }
    @Override protected void onDestroy() { web.destroy(); super.onDestroy(); }
}
