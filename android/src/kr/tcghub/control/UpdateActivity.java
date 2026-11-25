package kr.tcghub.control;

import android.app.Activity;
import android.os.Bundle;

public final class UpdateActivity extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        HubUi ui = new HubUi(this, "A90 서버 관리", true);
        boolean publicProfile = getIntent().getBooleanExtra("publicProfile", false);
        if (!publicProfile) SetupPanel.add(ui, ui.body, true);
        if (publicProfile || !getIntent().getBooleanExtra("profileKnown", false)) {
            SetupPanel.addPublicGuide(ui);
        }
    }
}
