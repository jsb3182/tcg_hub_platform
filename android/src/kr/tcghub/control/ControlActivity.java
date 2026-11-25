package kr.tcghub.control;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class ControlActivity extends Activity {
    private EditText address;
    private SharedPreferences prefs;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("control", MODE_PRIVATE);
        HubUi ui = new HubUi(this, "TCG 허브", false);
        ui.heading(ui.body, "공개 사이트 열기", 40);
        TextView explanation = ui.label("공유받은 HTTPS 주소를 입력하세요.", 16, ui.muted, false);
        explanation.setLineSpacing(ui.dp(2), 1);
        ui.add(ui.body, explanation, 8);
        TextView label = ui.label("공개 사이트 주소", 14, ui.ink, true);
        ui.add(ui.body, label, 32);
        address = new EditText(this);
        address.setId(View.generateViewId());
        address.setSaveEnabled(false);
        label.setLabelFor(address.getId());
        address.setSingleLine();
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        address.setTextSize(17);
        address.setTextColor(ui.ink);
        address.setHintTextColor(ui.color(R.color.hint));
        address.setMinimumHeight(ui.dp(56));
        address.setBackground(ui.interactive(10, ui.color(R.color.sheet), ui.edge));
        ui.pad(address, 14, 10, 14, 10);
        address.setHint("https://cards.example.com");
        address.setText(
                state == null
                        ? prefs.getString("publicSite", prefs.getString("publicSuggestion", ""))
                        : state.getString("address", ""));
        address.setImeOptions(EditorInfo.IME_ACTION_GO);
        address.setOnEditorActionListener(
                (v, action, event) -> {
                    if (action != EditorInfo.IME_ACTION_GO) return false;
                    openSite();
                    return true;
                });
        ui.add(ui.body, address, 8);
        Button launch = ui.button("브라우저로 열기", HubUi.Action.FILLED, v -> openSite());
        launch.setCompoundDrawablesRelative(
                null,
                null,
                ui.icon(R.drawable.ic_external, ui.color(R.color.on_primary), 20),
                null);
        ui.pad(launch, 18, 12, 18, 12);
        launch.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        ui.add(ui.body, launch, 12);

        View space = new View(this);
        ui.body.addView(space, new LinearLayout.LayoutParams(1, ui.dp(44), 1));
        ui.rule(ui.body);
        LinearLayout server = ui.row();
        server.setMinimumHeight(ui.dp(80));
        server.setBackground(ui.interactive(8, ui.surface, Color.TRANSPARENT));
        server.setFocusable(true);
        server.setClickable(true);
        server.setContentDescription("A90 서버 관리, 이 기기의 서버 연결 및 제어");
        server.setOnClickListener(v -> startActivity(new Intent(this, ServerActivity.class)));
        ImageView host = ui.image(R.drawable.ic_host, ui.color(R.color.on_tonal), 24);
        host.setBackground(ui.shape(12, ui.tonal, Color.TRANSPARENT));
        ui.pad(host, 10, 10, 10, 10);
        server.addView(host, ui.size(44, 44));
        LinearLayout labels = ui.column();
        ui.pad(labels, 14, 0, 4, 0);
        labels.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        labels.addView(ui.label("A90 서버 관리", 16, ui.ink, true));
        labels.addView(ui.label("이 기기의 서버 연결 및 제어", 14, ui.muted, false));
        server.addView(labels, new LinearLayout.LayoutParams(0, HubUi.WRAP, 1));
        server.addView(ui.image(R.drawable.ic_right, ui.muted, 20), ui.size(20, 20));
        ui.add(ui.body, server, 4);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (address.length() == 0 && !address.hasFocus())
            address.setText(prefs.getString("publicSuggestion", ""));
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putString("address", address.getText().toString());
    }

    private void openSite() {
        String root = PublicSite.root(address.getText().toString());
        if (root.isEmpty()) {
            address.setError("공유받은 https:// 공개 도메인 주소를 입력하세요.");
            address.requestFocus();
            return;
        }
        address.setText(root);
        prefs.edit().putString("publicSite", root).apply();
        try {
            startActivity(
                    new Intent(Intent.ACTION_VIEW, Uri.parse(root))
                            .addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException ex) {
            address.setError("공개 사이트를 열 브라우저를 설치하세요.");
        }
    }
}
