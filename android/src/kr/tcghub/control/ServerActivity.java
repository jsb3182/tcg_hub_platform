package kr.tcghub.control;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

public final class ServerActivity extends Activity {
    private static final String AUTH = "com.termux.documents";
    private static final String FOLDER = "/data/data/com.termux/files/home/tcg-control";
    private static final String LOCAL = "http://127.0.0.1:8080";
    private static final Pattern PUBLIC =
            Pattern.compile("https://[a-zA-Z0-9-]+(?:\\.[a-zA-Z0-9-]+)+");
    private static final int FLAGS =
            Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
    private static final String[] SERVICE_KEYS = {"db", "api", "worker", "tunnel"};
    private static final String[] SERVICE_NAMES = {"데이터베이스", "웹 서버", "수집 워커", "공개 터널"};
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Handler ui = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;
    private Uri tree;
    private String origin = "", pending = "";
    private long started, timeout;
    private boolean active, polling, ready, folderError;
    private boolean servicesStopped, profileRunning;
    private HubUi screen;
    private TextView summary, profile, address, message;
    private final TextView[] serviceValues = new TextView[SERVICE_KEYS.length];
    private LinearLayout connect, dashboard, operations, shareActions;
    private Button start, stop, status, browser, pair, reconnect;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("control", MODE_PRIVATE);
        String saved = prefs.getString("tree", "");
        if (!saved.isEmpty()) tree = Uri.parse(saved);
        pending = prefs.getString("pending", "");
        started = prefs.getLong("started", 0);
        timeout = prefs.getLong("timeout", 60_000);
        screen = new HubUi(this, "A90 서버 관리", true);
        connect = screen.column();
        screen.add(screen.body, connect, 0);
        SetupPanel.add(screen, connect, false);
        TextView section = screen.label("설치한 서버 연결", 20, screen.ink, true);
        section.setAccessibilityHeading(true);
        screen.add(connect, section, 32);
        TextView hint =
                screen.label(
                        "설치가 끝나면 Termux 저장소의 tcg-control 폴더를 선택해 접근을 허용하세요.",
                        16,
                        screen.muted,
                        false);
        hint.setLineSpacing(screen.dp(2), 1);
        screen.add(connect, hint, 8);
        pair = screen.button("Termux 제어 폴더 연결", HubUi.Action.OUTLINED, v -> chooseFolder());
        screen.add(connect, pair, 20);

        dashboard = screen.column();
        screen.add(screen.body, dashboard, 0);
        summary = screen.heading(dashboard, "상태 확인 중", 24);
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
        start = screen.button("서버 켜기", HubUi.Action.FILLED, v -> confirm(true));
        stop = screen.button("서버 끄기", HubUi.Action.OUTLINED, v -> confirm(false));
        screen.sideBySide(operations, start, stop, 16);

        LinearLayout top = screen.row();
        TextView title = screen.label("서비스 상태", 19, screen.ink, true);
        title.setAccessibilityHeading(true);
        top.addView(title, new LinearLayout.LayoutParams(0, HubUi.WRAP, 1));
        status = screen.iconButton(R.drawable.ic_refresh, "상태 새로고침", v -> request("status"));
        top.addView(status, screen.size(48, 48));
        screen.add(operations, top, 18);
        screen.rule(operations);
        for (int i = 0; i < SERVICE_KEYS.length; i++) {
            LinearLayout row = screen.row();
            row.setMinimumHeight(screen.dp(42));
            row.setScreenReaderFocusable(true);
            row.addView(
                    screen.label(SERVICE_NAMES[i], 16, screen.ink, false),
                    new LinearLayout.LayoutParams(0, HubUi.WRAP, 1));
            serviceValues[i] = screen.label("확인 전", 15, screen.muted, true);
            row.addView(serviceValues[i]);
            screen.add(operations, row, 0);
            screen.rule(operations);
        }
        browser = screen.button("관리자 화면 열기", HubUi.Action.TONAL, v -> openAdmin());
        screen.add(operations, browser, 16);
        shareActions = screen.column();
        screen.add(operations, shareActions, 0);
        screen.sideBySide(
                shareActions,
                screen.button("공개 주소 복사", HubUi.Action.OUTLINED, v -> sharePublicSite(false)),
                screen.button("공개 주소 공유", HubUi.Action.OUTLINED, v -> sharePublicSite(true)),
                8);
        reconnect = screen.button("제어 폴더 다시 연결", HubUi.Action.OUTLINED, v -> chooseFolder());
        screen.add(operations, reconnect, 8);
        Button guide =
                screen.button(
                        "서버 업데이트 안내",
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

    private void sharePublicSite(boolean useShareSheet) {
        String root = PublicSite.root(origin);
        if (tree == null || root.isEmpty()) return;
        if (useShareSheet) {
            Intent shareUrl =
                    new Intent(Intent.ACTION_SEND)
                            .setType("text/plain")
                            .putExtra(Intent.EXTRA_TEXT, root);
            startActivity(Intent.createChooser(shareUrl, "공개 주소 공유"));
        } else {
            ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            clipboard.setPrimaryClip(ClipData.newPlainText("TCG 허브", root));
            Toast.makeText(this, "공개 주소를 복사했습니다.", Toast.LENGTH_SHORT).show();
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
            note("기기에서 요청 결과를 확인하고 있습니다.");
            poll();
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
        io.shutdownNow();
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
        start.setEnabled(idle && !origin.isEmpty() && !profileRunning);
        stop.setEnabled(idle && !servicesStopped);
        browser.setEnabled(idle && ready && !origin.isEmpty());
        screen.colors(browser, profileRunning ? HubUi.Action.FILLED : HubUi.Action.TONAL);
    }

    private void chooseFolder() {
        Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        pick.addFlags(
                FLAGS
                        | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                        | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        pick.putExtra(
                DocumentsContract.EXTRA_INITIAL_URI,
                DocumentsContract.buildDocumentUri(AUTH, FOLDER));
        try {
            startActivityForResult(pick, 41);
        } catch (ActivityNotFoundException ex) {
            note("시스템 파일 선택기를 열 수 없습니다.");
        }
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code, result, data);
        if (code != 41 || result != RESULT_OK || data == null || data.getData() == null) return;
        Uri selected = data.getData();
        int flags = data.getFlags() & FLAGS;
        if (!"content".equals(selected.getScheme())
                || !AUTH.equals(selected.getAuthority())
                || !DocumentsContract.isTreeUri(selected)
                || !FOLDER.equals(DocumentsContract.getTreeDocumentId(selected))
                || flags != FLAGS) {
            folderError = true;
            note("Termux 저장소 안의 tcg-control 폴더만 선택하세요.");
            return;
        }
        try {
            getContentResolver().takePersistableUriPermission(selected, FLAGS);
            tree = selected;
            prefs.edit().putString("tree", tree.toString()).apply();
            updateButtons();
        } catch (SecurityException ex) {
            folderError = true;
            note("폴더 읽기·쓰기 권한을 다시 허용하세요.");
        }
    }

    private void confirm(boolean poweringOn) {
        final String action =
                poweringOn ? (LOCAL.equals(origin) ? "start-local" : "start-public") : "stop";
        new AlertDialog.Builder(this)
                .setTitle(poweringOn ? "서버를 켤까요?" : "서버를 끌까요?")
                .setMessage(
                        !poweringOn
                                ? "수집 워커와 웹 서버, 데이터베이스를 차례로 종료합니다."
                                : LOCAL.equals(origin)
                                        ? "A90 내부에서만 웹 서버를 시작합니다."
                                        : origin + "에서 접속할 수 있도록 Cloudflare 터널과 서버를 시작합니다.")
                .setNegativeButton("취소", null)
                .setPositiveButton(poweringOn ? "켜기" : "끄기", (d, w) -> request(action))
                .show();
    }

    private void openAdmin() {
        if (!(LOCAL.equals(origin) || PUBLIC.matcher(origin).matches())) return;
        try {
            startActivity(
                    new Intent(Intent.ACTION_VIEW, Uri.parse(origin + "/login?to=admin"))
                            .addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException ex) {
            note("관리자 화면을 열 브라우저를 설치하세요.");
        }
    }

    private void request(String action) {
        if (!pending.isEmpty() || tree == null) return;
        String id = UUID.randomUUID().toString().replace("-", "");
        long now = System.currentTimeMillis();
        pending = id;
        started = now;
        timeout = action.equals("status") ? 60_000 : 12 * 60_000;
        prefs.edit()
                .putString("pending", id)
                .putLong("started", now)
                .putLong("timeout", timeout)
                .apply();
        updateButtons();
        note(action.equals("status") ? "상태를 확인하고 있습니다." : "Termux에서 요청을 처리하고 있습니다.");
        Uri parent = DocumentsContract.buildDocumentUriUsingTree(tree, FOLDER);
        io.execute(
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
                        runOnUiThread(this::poll);
                    } catch (Exception ex) {
                        runOnUiThread(() -> fail(id, "제어 폴더에 요청을 기록할 수 없습니다. 폴더 연결을 확인하세요."));
                    }
                });
    }

    private void poll() {
        if (!active || polling || pending.isEmpty()) return;
        final String id = pending;
        if (System.currentTimeMillis() - started > timeout
                || System.currentTimeMillis() + 1000 < started) {
            fail(id, "결과 대기가 끝났습니다. Termux를 열고 상태를 새로고침하세요.");
            return;
        }
        polling = true;
        Uri response =
                DocumentsContract.buildDocumentUriUsingTree(
                        tree, FOLDER + "/reply-" + id + ".json");
        io.execute(
                () -> {
                    JSONObject parsed = null;
                    boolean denied = false;
                    try (InputStream in = getContentResolver().openInputStream(response)) {
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
                                polling = false;
                                if (isDestroyed() || !id.equals(pending)) return;
                                if (permissionLost) {
                                    fail(id, "Termux 제어 폴더 접근 권한을 다시 허용하세요.");
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

    private void finishRequest() {
        pending = "";
        prefs.edit().remove("pending").remove("started").remove("timeout").apply();
        updateButtons();
    }

    private void fail(String id, String why) {
        if (isDestroyed() || !id.equals(pending)) return;
        origin = "";
        ready = false;
        servicesStopped = false;
        profileRunning = false;
        summary.setText("상태 확인 필요");
        for (TextView value : serviceValues) {
            value.setText("확인 전");
            value.setTextColor(screen.muted);
        }
        note(why);
        finishRequest();
    }

    private void show(String id, JSONObject response) {
        JSONObject services = response.optJSONObject("services");
        if (services == null) {
            fail(id, "요청을 완료하지 못했습니다. Termux와 제어 서비스 상태를 확인하세요.");
            return;
        }
        String candidate = response.optString("origin", "");
        origin = LOCAL.equals(candidate) || PUBLIC.matcher(candidate).matches() ? candidate : "";
        String publicRoot = PublicSite.root(origin);
        prefs.edit().putString("publicSuggestion", publicRoot).apply();
        ready = response.optBoolean("ready");
        servicesStopped = true;
        profileRunning = ready && !origin.isEmpty();
        for (int i = 0; i < SERVICE_KEYS.length; i++) {
            String state = services.optString(SERVICE_KEYS[i]);
            boolean up = state.equals("up");
            boolean localTunnel = SERVICE_KEYS[i].equals("tunnel") && LOCAL.equals(origin);
            if (!state.equals(localTunnel ? "down" : "up")) profileRunning = false;
            if (!state.equals("down")) servicesStopped = false;
            serviceValues[i].setText(up ? "실행 중" : state.equals("down") ? "중지" : "확인 필요");
            serviceValues[i].setTextColor(up ? screen.color(R.color.success) : screen.muted);
        }
        if (profileRunning) summary.setText("서버 실행 중");
        else if (servicesStopped) summary.setText("서버 중지됨");
        else summary.setText(ready ? "서비스 확인 필요" : "웹 서버 응답 없음");
        profile.setText(LOCAL.equals(origin) ? "이 기기에서만 접속" : "공개 주소로 접속");
        address.setText(origin);
        String result = response.optString("result");
        note(
                result.equals("ok")
                        ? (origin.isEmpty() ? "배포 설정에서 접속 주소를 확인하세요." : "")
                        : result.equals("profile-changed")
                                ? "접속 설정이 바뀌었습니다. 현재 주소를 확인하고 다시 시도하세요."
                                : "명령을 완료하지 못했습니다. Termux에서 tcgctl status를 확인하세요.");
        finishRequest();
    }
}
