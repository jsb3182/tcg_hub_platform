package kr.tcghub.control;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** The app prepares a fixed, verified command. The operator runs it in Termux. */
final class SetupPanel {
    private static final String PLAY = "https://play.google.com/store/apps/details?id=com.termux";
    private static final String FDROID = "https://f-droid.org/packages/com.termux/";
    private static final String PUBLIC_GUIDE =
            "https://github.com/jsb3182/tcg_hub_platform/blob/"
                    + SetupCommand.TAG
                    + "/docs/DEPLOYMENT.md#7-백업복구업데이트";

    private SetupPanel() {}

    static void add(HubUi ui, LinearLayout parent, boolean update) {
        ui.heading(parent, update ? ui.activity.getString(R.string.local_update) : ui.activity.getString(R.string.install_server), 28);
        TextView body =
                ui.label(
                        update
                                ? ui.activity.getString(R.string.paste_update_cmd)
                                : ui.activity.getString(R.string.paste_cmd),
                        16,
                        ui.muted,
                        false);
        body.setLineSpacing(ui.dp(2), 1);
        ui.add(parent, body, 8);
        ui.add(parent, ui.label(ui.activity.getString(R.string.server_version) + SetupCommand.TAG, 14, ui.muted, false), 14);

        String command = SetupCommand.forHashes(ReleasePin.HELPER, ReleasePin.ARCHIVE);
        TextView notice = ui.label("", 14, ui.muted, false);
        notice.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        notice.setVisibility(View.GONE);
        Button copy =
                ui.button(
                        update ? ui.activity.getString(R.string.copy_update) : ui.activity.getString(R.string.copy_install),
                        HubUi.Action.FILLED,
                        v -> {
                            ClipboardManager clipboard =
                                    (ClipboardManager)
                                            ui.activity.getSystemService(Context.CLIPBOARD_SERVICE);
                            clipboard.setPrimaryClip(
                                    ClipData.newPlainText("TCG 허브 " + SetupCommand.TAG, command));
                            notice.setText(ui.activity.getString(R.string.command_copied));
                            notice.setVisibility(View.VISIBLE);
                        });
        ui.add(parent, copy, 14);
        ui.add(
                parent,
                ui.button(ui.activity.getString(R.string.termux_open), HubUi.Action.OUTLINED, v -> openTermux(ui.activity)),
                8);
        ui.add(parent, notice, 8);
    }

    static void addPublicGuide(HubUi ui) {
        ui.heading(ui.body, ui.activity.getString(R.string.public_update), 28);
        ui.add(
                ui.body,
                ui.label(
                        ui.activity.getString(R.string.public_update_detail), 16, ui.muted, false),
                8);
        ui.add(
                ui.body,
                ui.button(
                        ui.activity.getString(R.string.public_update_guide),
                        HubUi.Action.FILLED,
                        v -> openUrl(ui.activity, PUBLIC_GUIDE)),
                16);
        ui.add(
                ui.body,
                ui.button(ui.activity.getString(R.string.continue_termux), HubUi.Action.OUTLINED, v -> openTermux(ui.activity)),
                8);
    }

    static void openTermux(Activity activity) {
        Intent intent =
                new Intent(Intent.ACTION_MAIN)
                        .addCategory(Intent.CATEGORY_LAUNCHER)
                        .setClassName("com.termux", "com.termux.app.TermuxActivity")
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            activity.startActivity(intent);
        } catch (ActivityNotFoundException | SecurityException unavailable) {
            new AlertDialog.Builder(activity)
                    .setTitle(activity.getString(R.string.termux_open))
                    .setMessage(
                            activity.getString(R.string.termux_missing))
                    .setPositiveButton("Google Play", (dialog, which) -> openUrl(activity, PLAY))
                    .setNeutralButton("F-Droid", (dialog, which) -> openUrl(activity, FDROID))
                    .setNegativeButton(activity.getString(R.string.cancel), null)
                    .show();
        }
    }

    private static void openUrl(Activity activity, String url) {
        try {
            activity.startActivity(
                    new Intent(Intent.ACTION_VIEW, Uri.parse(url))
                            .addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException unavailable) {
            new AlertDialog.Builder(activity)
                    .setTitle(activity.getString(R.string.open_address))
                    .setMessage(url)
                    .setPositiveButton(activity.getString(R.string.close), null)
                    .show();
        }
    }
}
