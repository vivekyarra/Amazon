package dev.doneirl.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.util.TypedValue;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
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
 *
 * D-pad model: the web HUD owns arrow keys while it has focus (it moves focus between its
 * controls). Back (or Menu) always returns focus to the native view bar, so there is no trap.
 * Back on the view bar opens Ledger; Back on Ledger's bar exits the app.
 */
public final class MainActivity extends Activity {
    private static final String[][] VIEWS = {
        {"Ledger", "overview"}, {"Incident review", "incidents"}, {"Evidence packet", "evidence"}, {"Reality-Lock", "studio"}};
    private static final int MINT = Color.rgb(188, 246, 223);
    private static final int INK = Color.rgb(17, 31, 35);
    private static final String DEFAULT_STATUS = "Private household · check in-app source labels · in-app gate only · Back = view bar";

    private WebView web;
    private String base;
    private String page = "overview";
    private SharedPreferences prefs;
    private TextView status;
    private final Button[] viewButtons = new Button[VIEWS.length];
    private Button connectButton;
    private boolean loadFailed;
    private boolean networkLost;
    private ConnectivityManager connectivity;
    private ConnectivityManager.NetworkCallback networkCallback;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        prefs = getSharedPreferences("connection", MODE_PRIVATE);
        base = prefs.getString("base", "");
        page = prefs.getString("page", "overview");
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackgroundColor(INK);
        LinearLayout bar = new LinearLayout(this);
        // TV overscan-safe margins (~5%) and dp-sized, large focus targets.
        bar.setPadding(dp(48), dp(14), dp(48), dp(4));
        for (int i = 0; i < VIEWS.length; i++) {
            final String target = VIEWS[i][1];
            Button button = navButton(VIEWS[i][0]);
            button.setOnClickListener(v -> load(target));
            viewButtons[i] = button;
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(56), 1);
            lp.setMargins(dp(6), 0, dp(6), 0);
            bar.addView(button, lp);
        }
        connectButton = navButton("Connection");
        connectButton.setOnClickListener(v -> connection());
        LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(-2, dp(56));
        clp.setMargins(dp(6), 0, dp(6), 0);
        bar.addView(connectButton, clp);
        layout.addView(bar);
        status = new TextView(this);
        status.setTextColor(MINT);
        status.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        status.setText(DEFAULT_STATUS);
        status.setPadding(dp(54), dp(2), dp(54), dp(4));
        layout.addView(status);
        web = new WebView(this);
        web.setFocusable(true);
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
                return !(String.valueOf(u.getScheme()).equals(expected.getScheme())
                    && String.valueOf(u.getAuthority()).equals(expected.getAuthority()));
            }
            @Override public void onPageStarted(WebView v, String url, android.graphics.Bitmap favicon) { loadFailed = false; }
            @Override public void onPageFinished(WebView v, String url) {
                if (!loadFailed && !networkLost) status.setText(DEFAULT_STATUS);
            }
            @Override public void onReceivedError(WebView v, WebResourceRequest request, android.webkit.WebResourceError error) {
                if (request.isForMainFrame()) {
                    loadFailed = true;
                    status.setText("Connection unavailable. Retrying when the network returns; use Connection to change server. No promise was verified.");
                }
            }
        });
        layout.addView(web, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(layout);
        connectivity = getSystemService(ConnectivityManager.class);
        if (base.isEmpty()) { focusBar(viewButtons[0]); connection(); } else load(page);
    }

    private Button navButton(String label) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        b.setSingleLine(true);
        b.setFocusable(true);
        b.setFocusableInTouchMode(true);
        b.setPadding(dp(10), 0, dp(10), 0);
        StateListDrawable bg = new StateListDrawable();
        bg.addState(new int[]{android.R.attr.state_focused}, shape(MINT, Color.WHITE, 4));
        bg.addState(new int[]{android.R.attr.state_selected}, shape(Color.rgb(36, 66, 62), MINT, 2));
        bg.addState(new int[]{}, shape(Color.rgb(30, 46, 50), Color.rgb(60, 84, 88), 1));
        b.setBackground(bg);
        b.setTextColor(new ColorStateList(
            new int[][]{{android.R.attr.state_focused}, {}}, new int[]{INK, Color.WHITE}));
        b.setStateListAnimator(null);
        return b;
    }

    private GradientDrawable shape(int fill, int stroke, int strokeDp) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(fill);
        g.setCornerRadius(dp(10));
        g.setStroke(dp(strokeDp), stroke);
        return g;
    }

    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    private void load(String target) { load(target, true); }

    private void load(String target, boolean focusWeb) {
        if (base.isEmpty()) { connection(); return; }
        page = target;
        prefs.edit().putString("page", page).apply();
        for (int i = 0; i < VIEWS.length; i++) viewButtons[i].setSelected(VIEWS[i][1].equals(page));
        web.loadUrl(base + "/?tv=1&page=" + page);
        web.clearHistory();
        if (focusWeb) focusWeb();
    }

    /** Hand the remote to the web HUD. */
    private void focusWeb() {
        web.setFocusable(true);
        web.setFocusableInTouchMode(true);
        web.requestFocus();
    }

    /** Park the remote on the native view bar. The WebView is made unfocusable meanwhile so
     *  page scripts (autofocus, live refresh) cannot steal focus back; DPAD_DOWN returns to it. */
    private void focusBar(Button target) {
        web.setFocusable(false);
        web.setFocusableInTouchMode(false);
        target.requestFocus();
    }

    private Button currentButton() {
        for (int i = 0; i < VIEWS.length; i++) if (VIEWS[i][1].equals(page)) return viewButtons[i];
        return viewButtons[0];
    }

    private void connection() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        input.setHint("https://your-private-backend.example");
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setImeOptions(EditorInfo.IME_ACTION_GO);
        input.setText(base);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Your DONE/IRL backend").setMessage("Use a private HTTPS service. Debug builds also allow a local development HTTP server. Sign in with owner or judge credentials on the next screen.")
            .setView(input).setPositiveButton("Connect", (d, which) -> connectTo(input.getText().toString()))
            .setNegativeButton("Cancel", null).create();
        // Remote keyboards submit with Go/Enter; the Connect button stays reachable with D-pad Down.
        input.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_GO || actionId == EditorInfo.IME_ACTION_DONE
                || (event != null && event.getKeyCode() == KeyEvent.KEYCODE_ENTER && event.getAction() == KeyEvent.ACTION_UP)) {
                dialog.dismiss();
                connectTo(input.getText().toString());
                return true;
            }
            return false;
        });
        dialog.show();
    }

    private void connectTo(String raw) {
        String value = raw.trim().replaceAll("/+$", "");
        Uri uri = Uri.parse(value);
        boolean scheme = "https".equals(uri.getScheme()) || (BuildConfig.DEBUG && "http".equals(uri.getScheme()));
        if (!scheme || uri.getHost() == null || uri.getUserInfo() != null || (uri.getPath()!=null && !uri.getPath().isEmpty())) {
            status.setText("Enter a valid origin URL. Release builds require HTTPS."); return;
        }
        base = value;
        prefs.edit().putString("base", base).apply();
        load("overview");
    }

    private boolean barHasFocus() {
        View f = getCurrentFocus();
        if (f == connectButton) return true;
        for (Button b : viewButtons) if (f == b) return true;
        return false;
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        int code = event.getKeyCode();
        if (code == KeyEvent.KEYCODE_BACK || code == KeyEvent.KEYCODE_MENU) {
            // Consume DOWN so the web content never sees it; act once on UP.
            if (event.getAction() != KeyEvent.ACTION_UP) return true;
            if (!barHasFocus()) {
                focusBar(currentButton());
            } else if (code == KeyEvent.KEYCODE_BACK) {
                if (!"overview".equals(page)) { load("overview", false); focusBar(viewButtons[0]); }
                else finish();
            }
            return true;
        }
        if (code == KeyEvent.KEYCODE_DPAD_DOWN && barHasFocus() && !web.isFocusable()) {
            if (event.getAction() == KeyEvent.ACTION_UP) focusWeb();
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    @Override protected void onPause() {
        web.onPause();
        CookieManager.getInstance().flush();
        if (networkCallback != null) {
            try { connectivity.unregisterNetworkCallback(networkCallback); } catch (RuntimeException ignored) { }
            networkCallback = null;
        }
        super.onPause();
    }

    @Override protected void onResume() {
        super.onResume();
        web.onResume();
        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network network) {
                runOnUiThread(() -> {
                    boolean recover = networkLost || loadFailed;
                    networkLost = false;
                    if (recover && !base.isEmpty()) { status.setText("Network back. Reloading live ledger…"); load(page); }
                });
            }
            @Override public void onLost(Network network) {
                runOnUiThread(() -> {
                    networkLost = true;
                    status.setText("Network lost. Showing last loaded state; nothing new is verified until reconnect.");
                });
            }
        };
        try { connectivity.registerDefaultNetworkCallback(networkCallback); } catch (RuntimeException e) { networkCallback = null; }
        // After suspension the session may have lapsed or the server restarted: retry a failed load.
        if (loadFailed && !base.isEmpty()) load(page);
    }

    @Override protected void onDestroy() { web.destroy(); super.onDestroy(); }
}
