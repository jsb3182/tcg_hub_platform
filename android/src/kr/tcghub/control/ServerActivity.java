package kr.tcghub.control;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.AssetFileDescriptor;
import android.net.Uri;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import android.provider.DocumentsContract;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.Future;
import java.util.regex.Pattern;

public final class ServerActivity extends LocalizedActivity {
    private static final String LOCAL = "http://127.0.0.1:8080";
    private static final Pattern PUBLIC =
            Pattern.compile("https://[a-zA-Z0-9-]+(?:\\.[a-zA-Z0-9-]+)+");
    private static final String[] SERVICE_KEYS = {"db", "api", "worker", "tunnel"};
    private static final int[] SERVICE_NAMES = {R.string.database, R.string.web_server, R.string.worker, R.string.tunnel};
    private final Handler ui = new Handler(Looper.getMainLooper());
    private Future<?> operation;
    private CancellationSignal readCancel;
    private Runnable watchdog;
    private SharedPreferences prefs;
    private Uri tree;
    private String origin = "", pending = "";
    private long started, timeout;
    private boolean active, polling, ready, folderError;
    private boolean statusRequest;
    private boolean servicesStopped, profileRunning;
    private HubUi screen;
    private TextView summary, profile, address, message;
    private final TextView[] serviceValues = new TextView[SERVICE_KEYS.length];
    private LinearLayout connect, dashboard, operations, shareActions;
    private Button start, stop, status, browser, platform, pair, reconnect, adminSetup;
    private boolean supportsAdminSetup;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("control", MODE_PRIVATE);
        tree = ControlFolder.paired(getContentResolver(), prefs.getString("tree", ""));
        if (tree != null) pending = prefs.getString("pending", "");
        started = prefs.getLong("started", 0);
        timeout = prefs.getLong("timeout", 60_000);
        statusRequest = prefs.getBoolean("pendingStatus", timeout == 60_000);
        screen = new HubUi(this, getString(R.string.local_server), true);
        connect = screen.column();
        screen.add(screen.body, connect, 0);
        SetupPanel.add(screen, connect, false);
        TextView section = screen.label(getString(R.string.connect_installed), 20, screen.ink, true);
        section.setAccessibilityHeading(true);
        screen.add(connect, section, 32);
        TextView hint =
                screen.label(
                        getString(R.string.setup_folder_hint),
                        16,
                        screen.muted,
                        false);
        hint.setLineSpacing(screen.dp(2), 1);
        screen.add(connect, hint, 8);
        pair = screen.button(getString(R.string.pair_folder), HubUi.Action.OUTLINED, v -> chooseFolder());
        screen.add(connect, pair, 20);

        dashboard = screen.column();
        screen.add(screen.body, dashboard, 0);
        summary = screen.heading(dashboard, getString(R.string.checking_status), 24);
        profile = screen.label("", 16, screen.color(R.color.on_tonal), true);
        address = screen.label("", 15, screen.muted, false);
        address.setTextIsSelectable(true);
        screen.add(dashboard, profile, 8);
        screen.add(dashboard, address, 2);

        message = screen.label("", 15, screen.muted, false);
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        screen.add(screen.body, message, 10);
        note("");
        operations = screen.column();
        screen.add(screen.body, operations, 0);
        start = screen.button(getString(R.string.start_server), HubUi.Action.FILLED, v -> confirm(true));
        stop = screen.button(getString(R.string.stop_server), HubUi.Action.OUTLINED, v -> confirm(false));
        screen.sideBySide(operations, start, stop, 16);

        LinearLayout top = screen.row();
        TextView title = screen.label(getString(R.string.service_status), 19, screen.ink, true);
        title.setAccessibilityHeading(true);
        top.addView(title, new LinearLayout.LayoutParams(0, HubUi.WRAP, 1));
        status = screen.iconButton(R.drawable.ic_refresh, getString(R.string.refresh_status), v -> request("status"));
        top.addView(status, screen.size(48, 48));
        screen.add(operations, top, 18);
        screen.rule(operations);
        for (int i = 0; i < SERVICE_KEYS.length; i++) {
            LinearLayout row = screen.row();
            row.setMinimumHeight(screen.dp(42));
            row.setScreenReaderFocusable(true);
            row.addView(
                    screen.label(getString(SERVICE_NAMES[i]), 16, screen.ink, false),
                    new LinearLayout.LayoutParams(0, HubUi.WRAP, 1));
            serviceValues[i] = screen.label(getString(R.string.unchecked), 15, screen.muted, true);
            row.addView(serviceValues[i]);
            screen.add(operations, row, 0);
            screen.rule(operations);
        }
        browser = screen.button(getString(R.string.open_admin), HubUi.Action.TONAL, v -> openAdmin());
        screen.add(operations, browser, 16);
        adminSetup = screen.button(getString(R.string.admin_setup), HubUi.Action.OUTLINED, v -> adminGuide());
        screen.add(operations, adminSetup, 8);
        platform = screen.button(getString(R.string.open_catalog), HubUi.Action.OUTLINED, v -> openCatalog());
        screen.add(operations, platform, 8);
        shareActions = screen.column();
        screen.add(operations, shareActions, 0);
        screen.sideBySide(
                shareActions,
                screen.button(getString(R.string.copy_url), HubUi.Action.OUTLINED, v -> sharePublicSite(false)),
                screen.button(getString(R.string.share_url), HubUi.Action.OUTLINED, v -> sharePublicSite(true)),
                8);
        reconnect = screen.button(getString(R.string.pair_again), HubUi.Action.OUTLINED, v -> chooseFolder());
        screen.add(operations, reconnect, 8);
        Button guide =
                screen.button(
                        getString(R.string.update_info),
                        HubUi.Action.OUTLINED,
                        v ->
                                startActivity(
                                        new Intent(this, UpdateActivity.class)
                                                .putExtra("profileKnown", !origin.isEmpty())
                                                .putExtra(
                                                        "publicProfile",
                                                        !PublicSite.root(origin).isEmpty())));
        screen.add(operations, guide, 8);
        updateButtons();
    }

    private void note(String text) {
        message.setText(text);
        message.setVisibility(text.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private String catalogRoot() {
        return PlatformOrigin.pairedRoot(origin, prefs.getString("publicSuggestion", ""));
    }

    private void openCatalog() {
        tree = ControlFolder.paired(getContentResolver(), prefs.getString("tree", ""));
        if (tree == null) {
            pending = "";
            updateButtons();
            return;
        }
        String selected = catalogRoot();
        if (!selected.isEmpty()) PlatformActivity.openSelected(this, selected);
    }

    private void adminGuide() {
        if (tree == null || !LOCAL.equals(origin) || !ready || !pending.isEmpty()) return;
        AlertDialog.Builder dialog = new AlertDialog.Builder(this).setTitle(R.string.admin_setup)
                .setMessage(supportsAdminSetup ? R.string.admin_setup_detail : R.string.admin_old_detail)
                .setNegativeButton(R.string.cancel, null);
        if (supportsAdminSetup) {
            dialog.setPositiveButton(R.string.open_setup_termux, (d, w) -> request("admin-setup"))
                    .setNeutralButton(R.string.copy_admin_command, (d, w) -> copyAdminCommand("tcgctl admin-setup"));
        } else {
            dialog.setPositiveButton(R.string.copy_password, (d, w) -> copyAdminCommand("tcgctl password "))
                    .setNeutralButton(R.string.copy_totp, (d, w) -> copyAdminCommand("tcgctl totp "));
        }
        dialog.show();
    }

    private void copyAdminCommand(String command) {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        clipboard.setPrimaryClip(ClipData.newPlainText(getString(R.string.admin_setup), command));
        SetupPanel.openTermux(this);
    }

    private void sharePublicSite(boolean useShareSheet) {
        String root = PublicSite.root(origin);
        if (tree == null || root.isEmpty()) return;
        if (useShareSheet) {
            Intent shareUrl =
                    new Intent(Intent.ACTION_SEND)
                            .setType("text/plain")
                            .putExtra(Intent.EXTRA_TEXT, root);
            startActivity(Intent.createChooser(shareUrl, getString(R.string.share_url)));
        } else {
            ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            clipboard.setPrimaryClip(ClipData.newPlainText(getString(R.string.app_name), root));
            Toast.makeText(this, getString(R.string.copied_url), Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        active = true;
        if (folderError) {
            folderError = false;
            return;
        }
        if (tree == null) return;
        if (!pending.isEmpty()) {
            note(getString(R.string.waiting_request));
            if (armDeadline()) poll();
        } else {
            request("status");
        }
    }

    @Override
    protected void onPause() {
        active = false;
        ui.removeCallbacksAndMessages(null);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        cancelOperation();
        super.onDestroy();
    }

    private void updateButtons() {
        boolean idle = tree != null && pending.isEmpty();
        connect.setVisibility(tree == null ? View.VISIBLE : View.GONE);
        dashboard.setVisibility(tree == null ? View.GONE : View.VISIBLE);
        operations.setVisibility(tree == null ? View.GONE : View.VISIBLE);
        profile.setVisibility(origin.isEmpty() ? View.GONE : View.VISIBLE);
        address.setVisibility(origin.isEmpty() ? View.GONE : View.VISIBLE);
        boolean canShare = !PublicSite.root(origin).isEmpty();
        shareActions.setVisibility(idle && canShare ? View.VISIBLE : View.GONE);
        reconnect.setVisibility(tree == null ? View.GONE : View.VISIBLE);
        pair.setEnabled(pending.isEmpty());
        reconnect.setEnabled(pending.isEmpty());
        status.setEnabled(idle);
        start.setEnabled(idle && !profileRunning);
        stop.setEnabled(idle && !servicesStopped);
        browser.setEnabled(idle && ready && !origin.isEmpty());
        adminSetup.setVisibility(LOCAL.equals(origin) ? View.VISIBLE : View.GONE);
        adminSetup.setEnabled(idle && ready);
        platform.setEnabled(tree != null && !catalogRoot().isEmpty());
        screen.colors(browser, profileRunning ? HubUi.Action.FILLED : HubUi.Action.TONAL);
    }

    private void chooseFolder() {
        Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        pick.addFlags(
                ControlFolder.FLAGS
                        | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                        | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        pick.putExtra(
                DocumentsContract.EXTRA_INITIAL_URI,
                DocumentsContract.buildDocumentUri(ControlFolder.AUTHORITY, ControlFolder.ID));
        try {
            startActivityForResult(pick, 41);
        } catch (ActivityNotFoundException ex) {
            note(getString(R.string.no_picker));
        }
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code, result, data);
        if (code != 41 || result != RESULT_OK || data == null || data.getData() == null) return;
        Uri selected = data.getData();
        int flags = data.getFlags() & ControlFolder.FLAGS;
        if (!ControlFolder.matches(selected) || flags != ControlFolder.FLAGS) {
            folderError = true;
            note(getString(R.string.choose_folder));
            return;
        }
        try {
            getContentResolver().takePersistableUriPermission(selected, ControlFolder.FLAGS);
            tree = selected;
            prefs.edit().putString("tree", tree.toString()).apply();
            updateButtons();
        } catch (SecurityException ex) {
            folderError = true;
            note(getString(R.string.folder_permission));
        }
    }

    private void confirm(boolean poweringOn) {
        // Without a current profile, only request local start. The paired bridge independently checks it.
        boolean localStart = origin.isEmpty() || LOCAL.equals(origin);
        final String action =
                poweringOn ? (localStart ? "start-local" : "start-public") : "stop";
        new AlertDialog.Builder(this)
                .setTitle(poweringOn ? getString(R.string.confirm_start) : getString(R.string.confirm_stop))
                .setMessage(
                        !poweringOn
                                ? getString(R.string.stop_order)
                                : localStart
                                        ? getString(R.string.local_start_detail)
                                        : origin + getString(R.string.public_start_detail))
                .setNegativeButton(getString(R.string.cancel), null)
                .setPositiveButton(poweringOn ? getString(R.string.start) : getString(R.string.stop), (d, w) -> request(action))
                .show();
    }

    private void openAdmin() {
        if (!(LOCAL.equals(origin) || PUBLIC.matcher(origin).matches())) return;
        try {
            startActivity(
                    new Intent(Intent.ACTION_VIEW, Uri.parse(origin + "/login?to=admin"))
                            .addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException ex) {
            note(getString(R.string.admin_browser_needed));
        }
    }

    private void request(String action) {
        if (!pending.isEmpty() || tree == null) return;
        String id = UUID.randomUUID().toString().replace("-", "");
        long now = System.currentTimeMillis();
        pending = id;
        statusRequest = action.equals("status");
        started = now;
        timeout = action.equals("admin-setup") ? 45_000 : action.equals("status") ? 60_000 : 12 * 60_000;
        prefs.edit()
                .putString("pending", id)
                .putBoolean("pendingStatus", statusRequest)
                .putLong("started", now)
                .putLong("timeout", timeout)
                .apply();
        updateButtons();
        note(action.equals("status") ? getString(R.string.checking_services) : getString(R.string.processing));
        Uri parent = DocumentsContract.buildDocumentUriUsingTree(tree, ControlFolder.ID);
        if (!armDeadline()) return;
        submit(id,
                () -> {
                    try {
                        String filename = "request-" + now + "-" + id + "-" + action;
                        Uri created =
                                DocumentsContract.createDocument(
                                        getContentResolver(),
                                        parent,
                                        "application/octet-stream",
                                        filename);
                        if (created == null) throw new IOException();
                        runOnUiThread(() -> {
                            if (!acceptReply(id)) return;
                            if (action.equals("admin-setup") && active) SetupPanel.openTermux(this);
                            poll();
                        });
                    } catch (Exception ex) {
                        runOnUiThread(() -> fail(id, getString(R.string.unable_to_write)));
                    }
                });
    }

    private void poll() {
        if (!active || polling || pending.isEmpty()) return;
        final String id = pending;
        polling = true;
        Uri response =
                DocumentsContract.buildDocumentUriUsingTree(
                        tree, ControlFolder.ID + "/reply-" + id + ".json");
        CancellationSignal cancel = new CancellationSignal();
        readCancel = cancel;
        submit(id,
                () -> {
                    JSONObject parsed = null;
                    boolean denied = false;
                    try (AssetFileDescriptor descriptor = getContentResolver().openAssetFileDescriptor(response, "r", cancel);
                         InputStream in = descriptor == null ? null : descriptor.createInputStream()) {
                        if (in == null) throw new IOException();
                        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                        byte[] buf = new byte[512];
                        int n;
                        while ((n = in.read(buf)) != -1) {
                            if (bytes.size() + n > 4096) throw new IOException();
                            bytes.write(buf, 0, n);
                        }
                        parsed =
                                new JSONObject(
                                        new String(bytes.toByteArray(), StandardCharsets.UTF_8));
                    } catch (SecurityException ex) {
                        denied = true;
                    } catch (Exception ignored) {
                        /* Atomic reply does not exist while the command runs. */
                    }
                    JSONObject answer = parsed;
                    boolean permissionLost = denied;
                    runOnUiThread(
                            () -> {
                                if (!acceptReply(id)) return;
                                polling = false;
                                readCancel = null;
                                if (permissionLost) {
                                    fail(id, getString(R.string.regrant_folder));
                                    return;
                                }
                                if (answer != null) {
                                    show(id, answer);
                                    return;
                                }
                                if (active) ui.postDelayed(this::poll, 1000);
                            });
                });
    }

    private boolean armDeadline() {
        if (watchdog != null) ui.removeCallbacks(watchdog);
        String id = pending;
        long delay = MailboxIo.remaining(System.currentTimeMillis(), started, timeout);
        watchdog = () -> fail(id, getString(R.string.request_timeout));
        if (delay == 0) {
            watchdog.run();
            return false;
        }
        ui.postDelayed(watchdog, delay);
        return true;
    }

    private void submit(String id, Runnable task) {
        operation = MailboxIo.submit(statusRequest, task);
        if (operation == null) fail(id, getString(R.string.request_timeout));
    }

    private boolean acceptReply(String id) {
        if (isDestroyed() || !id.equals(pending)) return false;
        if (MailboxIo.remaining(System.currentTimeMillis(), started, timeout) > 0) return true;
        fail(id, getString(R.string.request_timeout));
        return false;
    }

    private void cancelOperation() {
        if (watchdog != null) ui.removeCallbacks(watchdog);
        MailboxIo.cancel(operation, readCancel == null ? null : readCancel::cancel);
        watchdog = null;
        operation = null;
        readCancel = null;
        polling = false;
    }

    private void finishRequest() {
        pending = "";
        cancelOperation();
        prefs.edit().remove("pending").remove("pendingStatus").remove("started").remove("timeout").apply();
        updateButtons();
    }

    private void fail(String id, String why) {
        if (isDestroyed() || !id.equals(pending)) return;
        origin = "";
        ready = false;
        servicesStopped = false;
        profileRunning = false;
        summary.setText(getString(R.string.status_needed));
        for (TextView value : serviceValues) {
            value.setText(getString(R.string.unchecked));
            value.setTextColor(screen.muted);
        }
        note(why);
        finishRequest();
    }

    private void show(String id, JSONObject response) {
        JSONObject services = response.optJSONObject("services");
        if (services == null) {
            fail(id, getString(R.string.control_error));
            return;
        }
        String candidate = response.optString("origin", "");
        origin = LOCAL.equals(candidate) || PUBLIC.matcher(candidate).matches() ? candidate : "";
        String publicRoot = PublicSite.root(origin);
        if (LOCAL.equals(origin) || !publicRoot.isEmpty()) prefs.edit().putString("publicSuggestion", publicRoot).apply();
        ready = response.optBoolean("ready");
        supportsAdminSetup = response.optBoolean("adminSetup");
        servicesStopped = true;
        profileRunning = ready && !origin.isEmpty();
        for (int i = 0; i < SERVICE_KEYS.length; i++) {
            String state = services.optString(SERVICE_KEYS[i]);
            boolean up = state.equals("up");
            boolean localTunnel = SERVICE_KEYS[i].equals("tunnel") && LOCAL.equals(origin);
            if (!state.equals(localTunnel ? "down" : "up")) profileRunning = false;
            if (!state.equals("down")) servicesStopped = false;
            serviceValues[i].setText(up ? getString(R.string.up) : state.equals("down") ? getString(R.string.down) : getString(R.string.unknown));
            serviceValues[i].setTextColor(up ? screen.color(R.color.success) : screen.muted);
        }
        if (profileRunning) summary.setText(getString(R.string.running_server));
        else if (servicesStopped) summary.setText(getString(R.string.stopped_server));
        else summary.setText(ready ? getString(R.string.check_service) : getString(R.string.web_down));
        profile.setText(LOCAL.equals(origin) ? getString(R.string.local_access) : getString(R.string.public_access));
        address.setText(origin);
        String result = response.optString("result");
        note(
                result.equals("session-open") ? getString(R.string.session_started)
                        : result.equals("session-unavailable") ? getString(R.string.session_unavailable)
                        : result.equals("ok")
                        ? (origin.isEmpty() ? getString(R.string.check_origin) : "")
                        : result.equals("profile-changed")
                                ? getString(R.string.profile_changed)
                                : getString(R.string.manage_command_error));
        finishRequest();
    }
}
