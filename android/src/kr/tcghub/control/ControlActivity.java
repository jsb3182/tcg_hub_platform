package kr.tcghub.control;

import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
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

public final class ControlActivity extends LocalizedActivity {
    private EditText address;
    private SharedPreferences prefs;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("control", MODE_PRIVATE);
        HubUi ui = new HubUi(this, getString(R.string.app_name), false);
        ui.heading(ui.body, getString(R.string.connect_platform), 28);
        TextView explanation = ui.label(getString(R.string.connect_intro), 16, ui.muted, false);
        explanation.setLineSpacing(ui.dp(2), 1);
        ui.add(ui.body, explanation, 8);
        TextView label = ui.label(getString(R.string.public_address), 14, ui.ink, true);
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
        Button launch = ui.button(getString(R.string.open_platform), HubUi.Action.FILLED, v -> openSite());
        launch.setCompoundDrawablesRelative(
                null,
                null,
                ui.icon(R.drawable.ic_right, ui.color(R.color.on_primary), 20),
                null);
        ui.pad(launch, 18, 12, 18, 12);
        launch.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        ui.add(ui.body, launch, 12);

        View space = new View(this);
        ui.body.addView(space, new LinearLayout.LayoutParams(1, ui.dp(32), 1));
        TextView tools = ui.label(getString(R.string.server_management), 15, ui.muted, true);
        tools.setAccessibilityHeading(true);
        ui.add(ui.body, tools, 0);
        addServerRow(ui, getString(R.string.remote_server), getString(R.string.remote_description), RemoteActivity.class);
        addServerRow(ui, getString(R.string.local_server), getString(R.string.local_description), ServerActivity.class);
        if (state == null && Intent.ACTION_MAIN.equals(getIntent().getAction())) {
            String saved = PlatformOrigin.launchRoot(prefs.getBoolean("lastWasLocal", false),
                    prefs.getString("publicSite", ""), prefs.getString("publicSuggestion", ""),
                    ControlFolder.paired(getContentResolver(), prefs.getString("tree", "")) != null);
            if (!saved.isEmpty()) PlatformActivity.open(this, saved);
        }
    }

    private void addServerRow(HubUi ui, String title, String subtitle, Class<?> destination) {
        ui.rule(ui.body);
        LinearLayout server = ui.row();
        server.setMinimumHeight(ui.dp(80));
        server.setBackground(ui.interactive(8, ui.surface, Color.TRANSPARENT));
        server.setFocusable(true);
        server.setClickable(true);
        server.setContentDescription(title + ", " + subtitle);
        server.setOnClickListener(v -> startActivity(new Intent(this, destination)));
        int icon = destination == RemoteActivity.class ? R.drawable.ic_cloud : R.drawable.ic_host;
        ImageView host = ui.image(icon, ui.color(R.color.on_tonal), 24);
        host.setBackground(ui.shape(12, ui.tonal, Color.TRANSPARENT));
        ui.pad(host, 10, 10, 10, 10);
        server.addView(host, ui.size(44, 44));
        LinearLayout labels = ui.column();
        ui.pad(labels, 14, 0, 4, 0);
        labels.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        labels.addView(ui.label(title, 16, ui.ink, true));
        labels.addView(ui.label(subtitle, 14, ui.muted, false));
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
            address.setError(getString(R.string.enter_https));
            address.requestFocus();
            return;
        }
        address.setText(root);
        PlatformActivity.openSelected(this, root);
    }
}
