package kr.tcghub.control;

import android.app.Activity;
import android.os.Bundle;

public final class UpdateActivity extends LocalizedActivity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        HubUi ui = new HubUi(this, getString(R.string.local_server), true);
        boolean publicProfile = getIntent().getBooleanExtra("publicProfile", false);
        if (!publicProfile) SetupPanel.add(ui, ui.body, true);
        if (publicProfile || !getIntent().getBooleanExtra("profileKnown", false)) {
            SetupPanel.addPublicGuide(ui);
        }
    }
}
