package kr.tcghub.control;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONException;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

public final class RemoteActivity extends LocalizedActivity {
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private SharedPreferences prefs;
    private HubUi ui;
    private String root, targetMac, targetLan;
    private TextView health, detail, target;
    private Button refresh, wake;
    private boolean active, busy;
    private int epoch;
    private long pollUntil;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("control", MODE_PRIVATE);
        root = PublicSite.root(prefs.getString("publicSite", ""));
        ui = new HubUi(this, getString(R.string.remote_server), true);
        ui.heading(ui.body, getString(R.string.server_connection), 24);
        ui.add(ui.body, ui.label(root.isEmpty() ? getString(R.string.save_url_first) : root,
                15, ui.muted, false), 6);
        health = ui.label(getString(R.string.unchecked), 20, ui.ink, true);
        health.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        ui.add(ui.body, health, 24);
        detail = ui.label("", 15, ui.muted, false);
        ui.add(ui.body, detail, 4);
        refresh = ui.button(getString(R.string.check_connection), HubUi.Action.OUTLINED, v -> check());
        Button admin = ui.button(getString(R.string.open_console), HubUi.Action.FILLED,
                v -> PlatformActivity.browser(this, root + "admin"));
        admin.setEnabled(!root.isEmpty());
        ui.add(ui.body, admin, 16);
        ui.add(ui.body, refresh, 8);
        ui.add(ui.body, ui.label(getString(R.string.admin_explanation), 14, ui.muted, false), 8);
        ui.heading(ui.body, getString(R.string.pc_power), 32);
        target = ui.label("", 15, ui.muted, false);
        target.setTextIsSelectable(true);
        ui.add(ui.body, target, 6);
        wake = ui.button(getString(R.string.send_wake), HubUi.Action.OUTLINED, v -> confirmWake());
        ui.add(ui.body, wake, 14);
        Button configure = ui.button(getString(R.string.configure_target), HubUi.Action.OUTLINED, v -> configure());
        configure.setEnabled(!root.isEmpty());
        ui.add(ui.body, configure, 8);
        renderTarget();
    }

    private void renderTarget() {
        // A change in public origin always requires new explicit PC approval.
        boolean same = !root.isEmpty() && root.equals(prefs.getString("wolSite", ""));
        targetMac = same ? prefs.getString("wolMac", "") : "";
        targetLan = same ? prefs.getString("wolLan", "") : "";
        target.setText(targetMac.isEmpty() ? getString(R.string.register_mac)
                : targetMac + "\n" + targetLan);
        wake.setEnabled(!targetMac.isEmpty() && pollUntil == 0);
        refresh.setEnabled(!root.isEmpty() && !busy);
    }

    private static final class Wifi {
        final Network network;
        final WakePacket.Lan lan;
        Wifi(Network network, WakePacket.Lan lan) { this.network = network; this.lan = lan; }
    }

    private Wifi wifi() throws IOException {
        ConnectivityManager cm = getSystemService(ConnectivityManager.class);
        Network n = cm.getActiveNetwork();
        NetworkCapabilities caps = cm.getNetworkCapabilities(n);
        LinkProperties links = cm.getLinkProperties(n);
        if (caps != null && links != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
                && !caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) {
            for (LinkAddress address : links.getLinkAddresses()) {
                try { return new Wifi(n, new WakePacket.Lan(address.getAddress(), address.getPrefixLength())); }
                catch (IllegalArgumentException ignore) { /* May be an IPv6 address. */ }
            }
        }
        throw new IOException(getString(R.string.private_wifi));
    }

    private void configure() {
        final Wifi connected;
        try { connected = wifi(); } catch (IOException e) { detail.setText(e.getMessage()); return; }
        final EditText input = new EditText(this);
        input.setSingleLine();
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        input.setHint("02:11:22:33:44:55"); input.setContentDescription(getString(R.string.mac_address));
        input.setMinHeight(ui.dp(48)); input.setText(targetMac);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle(getString(R.string.configure_target))
                .setMessage(getString(R.string.trusted_network) + connected.lan.cidr + getString(R.string.mac_prompt))
                .setView(input).setPositiveButton(getString(R.string.save), null).setNegativeButton(getString(R.string.cancel), null).create();
        dialog.setOnShowListener(v -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(button -> {
            try {
                String saved = WakePacket.mac(input.getText().toString());
                Wifi now = wifi();
                if (!now.network.equals(connected.network) || !now.lan.cidr.equals(connected.lan.cidr))
                    throw new IOException(getString(R.string.wifi_changed_setup));
                prefs.edit().putString("wolSite", root).putString("wolMac", saved)
                        .putString("wolLan", now.lan.cidr).apply();
                renderTarget(); dialog.dismiss();
            } catch (IllegalArgumentException e) { input.setError(getString(R.string.invalid_mac)); }
            catch (IOException e) { input.setError(e.getMessage()); }
        }));
        dialog.show();
    }

    private void confirmWake() {
        final Wifi wifi;
        try { wifi = wifi(); } catch (IOException e) { detail.setText(e.getMessage()); return; }
        if (!wifi.lan.cidr.equals(targetLan)) { detail.setText(getString(R.string.registered_wifi)); return; }
        new AlertDialog.Builder(this).setTitle(getString(R.string.wake_confirm))
                .setMessage(getString(R.string.confirm_network) + targetLan + "\n" + targetMac)
                .setNegativeButton(getString(R.string.cancel), null).setPositiveButton(getString(R.string.send_wake), (d, w) -> send(wifi)).show();
    }

    private void send(Wifi approved) {
        final String mac = targetMac;
        final int token = epoch;
        wake.setEnabled(false);
        io.execute(() -> {
            try (DatagramSocket socket = new DatagramSocket()) {
                Wifi now = wifi();
                if (!now.network.equals(approved.network) || !now.lan.cidr.equals(approved.lan.cidr))
                    throw new IOException(getString(R.string.wifi_changed));
                now.network.bindSocket(socket);
                WakePacket.send(socket, now.lan.broadcast, 9, mac);
                main.post(() -> {
                    if (!active || epoch != token) return;
                    pollUntil = SystemClock.elapsedRealtime() + 120_000;
                    health.setText(getString(R.string.wake_sent));
                    detail.setText(getString(R.string.waiting_boot));
                    check();
                });
            } catch (IOException e) {
                main.post(() -> { if (active && epoch == token) {
                    detail.setText(getString(R.string.failed_wake)); renderTarget();
                }});
            }
        });
    }

    private static boolean ready(String root) throws IOException, JSONException {
        HttpURLConnection conn = (HttpURLConnection) new URL(root + "api/v1/games").openConnection();
        try {
            conn.setInstanceFollowRedirects(false); conn.setUseCaches(false);
            conn.setConnectTimeout(3500); conn.setReadTimeout(3500);
            conn.setRequestProperty("Accept", "application/json");
            if (conn.getResponseCode() != 200) return false;
            try (InputStream in = conn.getInputStream()) {
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                byte[] chunk = new byte[1024]; int n;
                while ((n = in.read(chunk)) != -1) {
                    if (bytes.size() + n > 16384) return false;
                    bytes.write(chunk, 0, n);
                }
                JSONArray games = new JSONArray(new String(bytes.toByteArray(), StandardCharsets.UTF_8));
                Set<String> codes = new HashSet<>();
                for (int i = 0; i < games.length(); i++) codes.add(games.getJSONObject(i).getString("code"));
                return codes.contains("YUGIOH") && codes.contains("POKEMON") && codes.contains("WEISS")
                        && codes.contains("NIVEL") && codes.contains("RIFTBOUND");
            }
        } finally { conn.disconnect(); }
    }

    private void check() {
        if (!active || busy || root.isEmpty()) return;
        final int token = epoch;
        busy = true; refresh.setEnabled(false);
        if (pollUntil == 0) health.setText(getString(R.string.checking_connection));
        io.execute(() -> {
            boolean connected;
            try { connected = ready(root); } catch (IOException | JSONException e) { connected = false; }
            final boolean up = connected;
            main.post(() -> {
                if (!active || token != epoch) return;
                busy = false;
                if (!up && pollUntil > SystemClock.elapsedRealtime()) {
                    main.postDelayed(this::check, 5000); return;
                }
                health.setText(up ? getString(R.string.server_online) : getString(R.string.no_response));
                detail.setText(up ? getString(R.string.api_connected) : getString(R.string.check_host));
                pollUntil = 0; renderTarget();
            });
        });
    }
    @Override protected void onResume() { super.onResume(); active = true; check(); }
    @Override protected void onPause() {
        active = false; epoch++; busy = false; pollUntil = 0;
        main.removeCallbacksAndMessages(null); renderTarget(); super.onPause();
    }
    @Override protected void onDestroy() { io.shutdownNow(); super.onDestroy(); }
}
