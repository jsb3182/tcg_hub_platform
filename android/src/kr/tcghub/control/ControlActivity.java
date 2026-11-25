package kr.tcghub.control;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipboardManager;
import android.content.ClipData;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.DocumentsContract;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
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

public final class ControlActivity extends Activity {
    private static final String AUTH = "com.termux.documents";
    private static final String FOLDER = "/data/data/com.termux/files/home/tcg-control";
    private static final String LOCAL = "http://127.0.0.1:8080";
    private static final Pattern PUBLIC = Pattern.compile("https://[a-zA-Z0-9-]+(?:\\.[a-zA-Z0-9-]+)+");
    private static final int FLAGS = Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION;
    private static final int GREEN = Color.rgb(21, 74, 60), INK = Color.rgb(17, 44, 38);
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Handler ui = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;
    private Uri tree;
    private String origin = "", pending = "";
    private long started, timeout;
    private boolean active, polling, ready;
    private TextView summary, details, message;
    private Button start, stop, status, browser, pair, copy, share;
    private EditText siteInput;
    private LinearLayout controls;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("control", MODE_PRIVATE);
        String saved = prefs.getString("tree", "");
        if (!saved.isEmpty()) tree = Uri.parse(saved);
        pending = prefs.getString("pending", "");
        started = prefs.getLong("started", 0);
        timeout = prefs.getLong("timeout", 60_000);
        getWindow().setStatusBarColor(INK);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Color.rgb(243, 246, 240));
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(dp(24), dp(28), dp(24), dp(24));
        column.setFocusableInTouchMode(true);
        scroll.addView(column);
        setContentView(scroll);
        text(column, "TCG 허브", 30, true);
        TextView label = text(column, "공개 사이트 주소", 16, true);
        siteInput = new EditText(this);
        siteInput.setId(View.generateViewId());
        siteInput.setSaveEnabled(false);
        label.setLabelFor(siteInput.getId());
        siteInput.setSingleLine();
        siteInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        siteInput.setHint("https://cards.example.com");
        siteInput.setText(prefs.getString("publicSite", ""));
        column.addView(siteInput);
        button(column, "공개 사이트 열기", true, v -> openPublicSite());
        Button toggle = button(column, "A90 서버 관리", false, v -> {
            boolean expand = controls.getVisibility() != View.VISIBLE;
            controls.setVisibility(expand ? View.VISIBLE : View.GONE);
            ((Button) v).setText(expand ? "A90 서버 관리 접기" : "A90 서버 관리");
        });
        controls = new LinearLayout(this);
        controls.setOrientation(LinearLayout.VERTICAL);
        column.addView(controls);
        boolean expanded = state != null ? state.getBoolean("expanded", tree != null) : tree != null;
        controls.setVisibility(expanded ? View.VISIBLE : View.GONE);
        if (expanded) toggle.setText("A90 서버 관리 접기");
        summary = text(controls, "상태 확인 전", 22, true);
        details = text(controls, "", 16, false);
        message = text(controls, "", 16, false);
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        copy = button(controls, "공개 주소 복사", false, v -> sharePublicSite(false));
        share = button(controls, "공개 주소 공유", false, v -> sharePublicSite(true));
        start = button(controls, "서버 켜기", true, v -> confirm(true));
        stop = button(controls, "서버 끄기", false, v -> confirm(false));
        status = button(controls, "상태 새로고침", false, v -> request("status"));
        browser = button(controls, "관리자 화면 열기", false, v -> openAdmin());
        pair = button(controls, "Termux 제어 폴더 연결", false, v -> chooseFolder());
        updateButtons();
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putBoolean("expanded", controls.getVisibility() == View.VISIBLE);
    }

    private void openPublicSite() {
        String root = PublicSite.root(siteInput.getText().toString());
        if (root.isEmpty()) {
            siteInput.setError("공유받은 https:// 공개 도메인 주소를 입력하세요.");
            siteInput.requestFocus();
            return;
        }
        siteInput.setText(root);
        prefs.edit().putString("publicSite", root).apply();
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(root)).addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException ex) {
            siteInput.setError("공개 사이트를 열 브라우저를 설치하세요.");
        }
    }

    private void sharePublicSite(boolean useShareSheet) {
        String root = PublicSite.root(origin);
        if (tree == null || root.isEmpty()) return;
        if (useShareSheet) {
            Intent shareUrl = new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, root);
            startActivity(Intent.createChooser(shareUrl, "공개 주소 공유"));
        } else {
            ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            clipboard.setPrimaryClip(ClipData.newPlainText("TCG 허브", root));
            Toast.makeText(this, "공개 주소를 복사했습니다.", Toast.LENGTH_SHORT).show();
        }
    }

    private int dp(int n) { return Math.round(n * getResources().getDisplayMetrics().density); }
    private TextView text(LinearLayout parent, String value, int size, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(INK);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        view.setPadding(0, dp(6), 0, dp(8));
        parent.addView(view);
        return view;
    }
    private Button button(LinearLayout parent, String title, boolean primary, View.OnClickListener listener) {
        Button view = new Button(this);
        view.setText(title);
        view.setAllCaps(false);
        view.setTextColor(primary ? Color.WHITE : INK);
        GradientDrawable shape = new GradientDrawable();
        shape.setCornerRadius(dp(12));
        shape.setColor(primary ? GREEN : Color.WHITE);
        shape.setStroke(dp(1), primary ? GREEN : Color.rgb(190, 204, 191));
        view.setBackground(shape);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, dp(52));
        lp.topMargin = dp(9);
        parent.addView(view, lp);
        view.setOnClickListener(listener);
        return view;
    }

    @Override protected void onResume() {
        super.onResume();
        active = true;
        if (tree == null) {
            message.setText("처음 한 번, Android 파일 선택기에서 Termux의 tcg-control 폴더를 허용하세요.");
        } else if (!pending.isEmpty()) {
            message.setText("기기에서 요청 결과를 확인하고 있습니다.");
            poll();
        } else {
            request("status");
        }
    }
    @Override protected void onPause() { active = false; ui.removeCallbacksAndMessages(null); super.onPause(); }
    @Override protected void onDestroy() { io.shutdownNow(); super.onDestroy(); }
    private void updateButtons() {
        boolean idle = tree != null && pending.isEmpty();
        int visibility = idle && !PublicSite.root(origin).isEmpty() ? View.VISIBLE : View.GONE;
        copy.setVisibility(visibility);
        share.setVisibility(visibility);
        for (Button button : new Button[]{start, stop, status, browser, pair}) {
            boolean enabled = button == pair ? pending.isEmpty()
                    : button == start ? idle && !origin.isEmpty()
                    : button == browser ? idle && ready && !origin.isEmpty() : idle;
            button.setEnabled(enabled);
            button.setAlpha(enabled ? 1f : 0.5f);
        }
    }

    private void chooseFolder() {
        Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        pick.addFlags(FLAGS | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        pick.putExtra(DocumentsContract.EXTRA_INITIAL_URI, DocumentsContract.buildDocumentUri(AUTH, FOLDER));
        try { startActivityForResult(pick, 41); }
        catch (ActivityNotFoundException ex) { message.setText("시스템 파일 선택기를 열 수 없습니다."); }
    }
    @Override protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code, result, data);
        if (code != 41 || result != RESULT_OK || data == null || data.getData() == null) return;
        Uri selected = data.getData();
        int flags = data.getFlags() & FLAGS;
        if (!"content".equals(selected.getScheme()) || !AUTH.equals(selected.getAuthority()) ||
                !DocumentsContract.isTreeUri(selected) || !FOLDER.equals(DocumentsContract.getTreeDocumentId(selected)) || flags != FLAGS) {
            message.setText("Termux 저장소 안의 tcg-control 폴더만 선택하세요.");
            return;
        }
        try {
            getContentResolver().takePersistableUriPermission(selected, FLAGS);
            tree = selected;
            prefs.edit().putString("tree", tree.toString()).apply();
            updateButtons();
        } catch (SecurityException ex) { message.setText("폴더 읽기·쓰기 권한을 다시 허용하세요."); }
    }
    private void confirm(boolean poweringOn) {
        final String action = poweringOn ? (LOCAL.equals(origin) ? "start-local" : "start-public") : "stop";
        new AlertDialog.Builder(this).setTitle(poweringOn ? "서버를 켤까요?" : "서버를 끌까요?")
                .setMessage(!poweringOn ? "수집 워커와 웹 서버, 데이터베이스를 차례로 종료합니다."
                        : LOCAL.equals(origin) ? "A90 내부에서만 웹 서버를 시작합니다."
                        : origin + "에서 접속할 수 있도록 Cloudflare 터널과 서버를 시작합니다.")
                .setNegativeButton("취소", null).setPositiveButton(poweringOn ? "켜기" : "끄기", (d, w) -> request(action)).show();
    }
    private void openAdmin() {
        if (!(LOCAL.equals(origin) || PUBLIC.matcher(origin).matches())) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(origin + "/login?to=admin")).addCategory(Intent.CATEGORY_BROWSABLE)); }
        catch (ActivityNotFoundException ex) { message.setText("관리자 화면을 열 브라우저를 설치하세요."); }
    }

    private void request(String action) {
        if (!pending.isEmpty() || tree == null) return;
        String id = UUID.randomUUID().toString().replace("-", "");
        long now = System.currentTimeMillis();
        pending = id;
        started = now;
        timeout = action.equals("status") ? 60_000 : 12 * 60_000;
        prefs.edit().putString("pending", id).putLong("started", now).putLong("timeout", timeout).apply();
        updateButtons();
        message.setText(action.equals("status") ? "상태를 확인하고 있습니다." : "Termux에서 요청을 처리하고 있습니다.");
        Uri parent = DocumentsContract.buildDocumentUriUsingTree(tree, FOLDER);
        io.execute(() -> {
            try {
                String filename = "request-" + now + "-" + id + "-" + action;
                Uri created = DocumentsContract.createDocument(getContentResolver(), parent, "application/octet-stream", filename);
                if (created == null) throw new IOException();
                runOnUiThread(this::poll);
            } catch (Exception ex) { runOnUiThread(() -> fail(id, "제어 폴더에 요청을 기록할 수 없습니다. 폴더 연결을 확인하세요.")); }
        });
    }
    private void poll() {
        if (!active || polling || pending.isEmpty()) return;
        final String id = pending;
        if (System.currentTimeMillis() - started > timeout || System.currentTimeMillis() + 1000 < started) {
            fail(id, "결과 대기가 끝났습니다. Termux를 열고 상태를 새로고침하세요.");
            return;
        }
        polling = true;
        Uri response = DocumentsContract.buildDocumentUriUsingTree(tree, FOLDER + "/reply-" + id + ".json");
        io.execute(() -> {
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
                parsed = new JSONObject(new String(bytes.toByteArray(), StandardCharsets.UTF_8));
            } catch (SecurityException ex) { denied = true; }
              catch (Exception ignored) { /* Atomic reply does not exist while the command runs. */ }
            JSONObject answer = parsed;
            boolean permissionLost = denied;
            runOnUiThread(() -> {
                polling = false;
                if (isDestroyed() || !id.equals(pending)) return;
                if (permissionLost) { fail(id, "Termux 제어 폴더 접근 권한을 다시 허용하세요."); return; }
                if (answer != null) { show(id, answer); return; }
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
        origin = ""; ready = false;
        summary.setText("상태 확인 필요"); details.setText(""); message.setText(why);
        finishRequest();
    }
    private void show(String id, JSONObject response) {
        JSONObject services = response.optJSONObject("services");
        if (services == null) { fail(id, "요청을 완료하지 못했습니다. Termux와 제어 서비스 상태를 확인하세요."); return; }
        String candidate = response.optString("origin", "");
        origin = LOCAL.equals(candidate) || PUBLIC.matcher(candidate).matches() ? candidate : "";
        String publicRoot = PublicSite.root(origin);
        if (!publicRoot.isEmpty() && siteInput.getText().length() == 0) siteInput.setText(publicRoot);
        ready = response.optBoolean("ready");
        summary.setText(ready ? "서버 실행 중" : "웹 서버 응답 없음");
        String[] keys = {"db", "api", "worker", "tunnel"};
        String[] names = {"데이터베이스", "웹 서버", "수집 워커", "공개 터널"};
        StringBuilder rows = new StringBuilder();
        for (int i = 0; i < keys.length; i++) {
            String state = services.optString(keys[i]);
            if (i > 0) rows.append('\n');
            rows.append(names[i]).append("   ").append(state.equals("up") ? "실행" : state.equals("down") ? "중지" : "확인 필요");
        }
        details.setText(rows.toString());
        String result = response.optString("result");
        message.setText(result.equals("ok") ? (origin.isEmpty() ? "배포 설정 확인 필요" : "접속 주소  " + origin)
                : result.equals("profile-changed") ? "접속 설정이 바뀌었습니다. 현재 주소를 확인하고 다시 시도하세요."
                : "명령을 완료하지 못했습니다. Termux에서 tcgctl status를 확인하세요.");
        finishRequest();
    }
}
