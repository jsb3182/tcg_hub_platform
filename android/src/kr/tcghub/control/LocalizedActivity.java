package kr.tcghub.control;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.res.Configuration;
import android.os.LocaleList;
import java.util.Locale;

abstract class LocalizedActivity extends Activity {
    static final String[] CODES = {"ko", "en", "ja"};
    static final String[] NAMES = {"한국어", "English", "日本語"};

    @Override protected void attachBaseContext(Context base) {
        String code = base.getSharedPreferences("control", MODE_PRIVATE).getString("language", "ko");
        Configuration config = new Configuration(base.getResources().getConfiguration());
        config.setLocales(new LocaleList(Locale.forLanguageTag(code)));
        super.attachBaseContext(base.createConfigurationContext(config));
    }

    void chooseLanguage() {
        String current = getSharedPreferences("control", MODE_PRIVATE).getString("language", "ko");
        int index = java.util.Arrays.asList(CODES).indexOf(current);
        new AlertDialog.Builder(this).setTitle(R.string.language)
                .setSingleChoiceItems(NAMES, index, (dialog, choice) -> {
                    getSharedPreferences("control", MODE_PRIVATE).edit()
                            .putString("language", CODES[choice]).putBoolean("sendLanguage", true).apply();
                    dialog.dismiss();
                    recreate();
                })
                .setNegativeButton(R.string.cancel, null).show();
    }
}
