package kr.tcghub.control;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.ServiceWorkerClient;
import android.webkit.ServiceWorkerController;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import java.io.ByteArrayInputStream;

public final class PlatformActivity extends LocalizedActivity {
    private PlatformOrigin origin;
    private WebView web;
    private LinearLayout problem;
    private ProgressBar progress;
    private boolean failed;

    static void open(Context context, String root) {
        context.startActivity(new Intent(context, PlatformActivity.class).putExtra("origin", root));
    }

    static void openSelected(Context context, String root) {
        boolean local = PlatformOrigin.LOCAL.equals(root);
        SharedPreferences.Editor choice = context.getSharedPreferences("control", MODE_PRIVATE).edit();
        choice.putBoolean("lastWasLocal", local);
        if (!local) choice.putString("publicSite", root);
        choice.apply();
        open(context, root);
    }

    static void browser(Context context, String url) {
        try {
            context.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)).addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(context, context.getString(R.string.install_browser), Toast.LENGTH_LONG).show();
        }
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        String selected = getIntent().getStringExtra("origin");
        if (selected == null) { finish(); return; }
        origin = new PlatformOrigin(selected);
        HubUi ui = new HubUi(this, getString(R.string.app_name), true);
        LinearLayout page = ui.column();
        page.setBackgroundColor(ui.surface);
        setContentView(page);
        if (Build.VERSION.SDK_INT >= 35) {
            page.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets b = insets.getInsets(WindowInsets.Type.systemBars()
                        | WindowInsets.Type.ime() | WindowInsets.Type.displayCutout());
                view.setPadding(b.left, b.top, b.right, b.bottom);
                return WindowInsets.CONSUMED;
            });
        }
        LinearLayout bar = ui.row();
        ui.pad(bar, 6, 2, 6, 2);
        bar.addView(ui.iconButton(R.drawable.ic_back, getString(R.string.settings), v -> finish()), ui.size(48,48));
        TextView hostname = ui.label(Uri.parse(origin.root).getHost(), 15, ui.ink, true);
        hostname.setSingleLine(true);
        hostname.setEllipsize(android.text.TextUtils.TruncateAt.END);
        bar.addView(hostname, new LinearLayout.LayoutParams(0, HubUi.WRAP, 1));
        bar.addView(ui.iconButton(R.drawable.ic_refresh, getString(R.string.reload), v -> load()), ui.size(48,48));
        bar.addView(ui.iconButton(R.drawable.ic_external, getString(R.string.open_browser), v -> {
            String current = web.getUrl();
            browser(this, current != null && origin.owns(current) ? current : origin.root);
        }), ui.size(48,48));
        page.addView(bar);
        ui.rule(page);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);
        progress.setContentDescription(getString(R.string.connecting));
        page.addView(progress, ui.size(HubUi.FILL, 3));
        problem = ui.column();
        ui.pad(problem, 24, 12, 24, 16);
        ui.heading(problem, getString(R.string.not_connected), 16);
        TextView reason = ui.label(getString(R.string.check_address), 16, ui.muted, false);
        reason.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        ui.add(problem, reason, 8);
        ui.add(problem, ui.button(getString(R.string.retry), HubUi.Action.FILLED, v -> load()), 20);
        ui.add(problem, ui.button(getString(R.string.settings), HubUi.Action.OUTLINED, v -> finish()), 8);
        page.addView(problem);
        problem.setVisibility(View.GONE);
        web = new WebView(this);
        web.setBackgroundColor(ui.surface);
        page.addView(web, new LinearLayout.LayoutParams(HubUi.FILL, 0, 1));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setAllowFileAccessFromFileURLs(false);
        s.setAllowUniversalAccessFromFileURLs(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setSafeBrowsingEnabled(true);
        s.setJavaScriptCanOpenWindowsAutomatically(false);
        s.setGeolocationEnabled(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        ServiceWorkerController sw = ServiceWorkerController.getInstance();
        sw.getServiceWorkerWebSettings().setAllowFileAccess(false);
        sw.getServiceWorkerWebSettings().setAllowContentAccess(false);
        final PlatformOrigin allowed = origin;
        sw.setServiceWorkerClient(new ServiceWorkerClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebResourceRequest request) {
                return filter(allowed, request);
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (!request.isForMainFrame()) return !allowed.resource(url);
                if (allowed.adminPage(url)) { browser(PlatformActivity.this, origin.root + "admin"); return true; }
                if (allowed.owns(url)) return false;
                if (request.hasGesture() && !PublicSite.root(url).isEmpty()) browser(PlatformActivity.this, url);
                return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return filter(allowed, request);
            }
            @Override public void onPageStarted(WebView v, String url, Bitmap icon) {
                if (!allowed.owns(url)) { v.stopLoading(); showFailure(); return; }
                failed = false; progress.setVisibility(View.VISIBLE);
            }
            @Override public void onPageFinished(WebView v, String url) {
                progress.setVisibility(View.GONE);
                if (!failed && allowed.owns(url)) getSharedPreferences("control", MODE_PRIVATE)
                        .edit().remove("sendLanguage").apply();
            }
            @Override public void onReceivedError(WebView v, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showFailure();
            }
            @Override public void onReceivedHttpError(WebView v, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 400) showFailure();
            }
        });
        if (state == null || web.restoreState(state) == null) load();
    }

    private static WebResourceResponse filter(PlatformOrigin allowed, WebResourceRequest request) {
        String url = request.getUrl().toString();
        if (allowed.owns(url) || (!request.isForMainFrame() && "GET".equals(request.getMethod()) && allowed.resource(url))) return null;
        return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked", null, new ByteArrayInputStream(new byte[0]));
    }

    private void load() {
        problem.setVisibility(View.GONE); web.setVisibility(View.VISIBLE);
        String current = web.getUrl();
        if (current != null && origin.owns(current)) {
            web.loadUrl(current);
        } else {
            android.content.SharedPreferences prefs = getSharedPreferences("control", MODE_PRIVATE);
            String lang = prefs.getString("language", "ko");
            boolean send = prefs.getBoolean("sendLanguage", false) && java.util.Arrays.asList(CODES).contains(lang);
            web.loadUrl(send ? origin.root + "?lang=" + lang : origin.root);
        }
    }
    private void showFailure() {
        failed = true; web.setVisibility(View.GONE); progress.setVisibility(View.GONE); problem.setVisibility(View.VISIBLE);
    }
    @Override protected void onSaveInstanceState(Bundle out) { super.onSaveInstanceState(out); web.saveState(out); }
    @Override public void onBackPressed() { if (!failed && web.canGoBack()) web.goBack(); else super.onBackPressed(); }
    @Override protected void onDestroy() {
        if (web != null) { ((LinearLayout) web.getParent()).removeView(web); web.destroy(); }
        super.onDestroy();
    }
}
