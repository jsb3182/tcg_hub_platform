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
        ui.heading(parent, update ? "로컬 서버 업데이트" : "A90에 서버 설치", 28);
        TextView body =
                ui.label(
                        update
                                ? "Termux에 명령을 붙여 넣고 Enter를 누르세요. 서버를 사용 중이라면 업데이트 동안 조회와 수집이"
                                        + " 잠시 중단됩니다."
                                : "Termux에 명령을 붙여 넣고 Enter를 누르세요.",
                        16,
                        ui.muted,
                        false);
        body.setLineSpacing(ui.dp(2), 1);
        ui.add(parent, body, 8);
        ui.add(parent, ui.label("서버 버전  " + SetupCommand.TAG, 14, ui.muted, false), 14);

        String command = SetupCommand.forHashes(ReleasePin.HELPER, ReleasePin.ARCHIVE);
        TextView notice = ui.label("", 14, ui.muted, false);
        notice.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        notice.setVisibility(View.GONE);
        Button copy =
                ui.button(
                        update ? "업데이트 명령 복사" : "설치 명령 복사",
                        HubUi.Action.FILLED,
                        v -> {
                            ClipboardManager clipboard =
                                    (ClipboardManager)
                                            ui.activity.getSystemService(Context.CLIPBOARD_SERVICE);
                            clipboard.setPrimaryClip(
                                    ClipData.newPlainText("TCG 허브 " + SetupCommand.TAG, command));
                            notice.setText("복사했습니다. Termux 터미널에 붙여 넣으세요.");
                            notice.setVisibility(View.VISIBLE);
                        });
        ui.add(parent, copy, 14);
        ui.add(
                parent,
                ui.button("Termux 열기", HubUi.Action.OUTLINED, v -> openTermux(ui.activity)),
                8);
        ui.add(parent, notice, 8);
    }

    static void addPublicGuide(HubUi ui) {
        ui.heading(ui.body, "공개 서버 업데이트", 28);
        ui.add(
                ui.body,
                ui.label(
                        "Cloudflare 공개 설정을 유지하려면 배포 가이드의 백업 및 업데이트 절차를 따르세요.", 16, ui.muted, false),
                8);
        ui.add(
                ui.body,
                ui.button(
                        "공개 서버 업데이트 절차",
                        HubUi.Action.FILLED,
                        v -> openUrl(ui.activity, PUBLIC_GUIDE)),
                16);
        ui.add(
                ui.body,
                ui.button("Termux에서 계속", HubUi.Action.OUTLINED, v -> openTermux(ui.activity)),
                8);
    }

    private static void openTermux(Activity activity) {
        Intent intent =
                new Intent(Intent.ACTION_MAIN)
                        .addCategory(Intent.CATEGORY_LAUNCHER)
                        .setClassName("com.termux", "com.termux.app.TermuxActivity")
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            activity.startActivity(intent);
        } catch (ActivityNotFoundException | SecurityException unavailable) {
            new AlertDialog.Builder(activity)
                    .setTitle("Termux 열기")
                    .setMessage(
                            "Termux를 열 수 없습니다. A90용 Termux를 설치한 뒤 한 번 실행하세요. 기존 사용자는 원래 설치한 배포처를"
                                    + " 이용하세요.")
                    .setPositiveButton("Google Play", (dialog, which) -> openUrl(activity, PLAY))
                    .setNeutralButton("F-Droid", (dialog, which) -> openUrl(activity, FDROID))
                    .setNegativeButton("취소", null)
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
                    .setTitle("브라우저에서 열 주소")
                    .setMessage(url)
                    .setPositiveButton("닫기", null)
                    .show();
        }
    }
}
