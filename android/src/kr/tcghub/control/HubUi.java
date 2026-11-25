package kr.tcghub.control;

import android.app.Activity;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.StateListDrawable;
import android.os.Build;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Native controls share the same color roles, type scale and minimum touch size. */
final class HubUi {
    enum Action {
        FILLED,
        TONAL,
        OUTLINED
    }

    static final int FILL = -1, WRAP = -2;
    private static final int[][] STATES = {{-android.R.attr.state_enabled}, {}};
    final Activity activity;
    final LinearLayout body;
    final int ink, muted, primary, surface, tonal, edge;

    HubUi(Activity activity, String title, boolean canGoBack) {
        this.activity = activity;
        ink = color(R.color.ink);
        muted = color(R.color.muted);
        primary = color(R.color.primary);
        surface = color(R.color.canvas);
        tonal = color(R.color.tonal);
        edge = color(R.color.edge);
        FrameLayout root = new FrameLayout(activity);
        root.setBackgroundColor(surface);
        // API 35 draws behind system bars by default. Earlier versions use the platform's fitted
        // window.
        if (Build.VERSION.SDK_INT >= 35) {
            root.setOnApplyWindowInsetsListener(
                    (v, insets) -> {
                        android.graphics.Insets bars =
                                insets.getInsets(
                                        WindowInsets.Type.systemBars()
                                                | WindowInsets.Type.displayCutout()
                                                | WindowInsets.Type.ime());
                        v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                        return WindowInsets.CONSUMED;
                    });
        }
        LinearLayout page = column();
        root.addView(page, new FrameLayout.LayoutParams(FILL, FILL, Gravity.CENTER_HORIZONTAL));
        root.addOnLayoutChangeListener(
                (v, l, t, r, b, ol, ot, or_, ob) -> {
                    int width =
                            Math.min(
                                    dp(632),
                                    r - l - root.getPaddingLeft() - root.getPaddingRight());
                    if (width > 0 && page.getLayoutParams().width != width) {
                        FrameLayout.LayoutParams lp =
                                (FrameLayout.LayoutParams) page.getLayoutParams();
                        lp.width = width;
                        page.setLayoutParams(lp);
                    }
                });
        LinearLayout bar = row();
        pad(bar, canGoBack ? 8 : 24, 5, 16, 5);
        bar.setMinimumHeight(dp(60));
        if (canGoBack) {
            Button back = iconButton(R.drawable.ic_back, "뒤로", v -> activity.finish());
            bar.addView(back, size(48, 48));
        } else {
            ImageView logo = image(R.drawable.ic_cards, primary, 25);
            logo.setBackground(shape(10, tonal, Color.TRANSPARENT));
            pad(logo, 7, 7, 7, 7);
            bar.addView(logo, size(40, 40));
        }
        TextView appName = label(title, 20, ink, true);
        pad(appName, canGoBack ? 4 : 12, 0, 0, 0);
        bar.addView(appName);
        page.addView(bar);
        rule(page);
        ScrollView scroll = new ScrollView(activity);
        scroll.setFillViewport(true);
        page.addView(scroll, new LinearLayout.LayoutParams(FILL, 0, 1));
        body = column();
        body.setFocusableInTouchMode(true);
        body.setDefaultFocusHighlightEnabled(false);
        pad(body, 24, 0, 24, 18);
        scroll.addView(body);
        activity.setContentView(root);
    }

    int color(int id) {
        return activity.getColor(id);
    }

    int dp(int value) {
        return Math.round(value * activity.getResources().getDisplayMetrics().density);
    }

    void pad(View v, int l, int t, int r, int b) {
        v.setPadding(dp(l), dp(t), dp(r), dp(b));
    }

    LinearLayout column() {
        LinearLayout layout = new LinearLayout(activity);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    LinearLayout row() {
        LinearLayout layout = new LinearLayout(activity);
        layout.setGravity(Gravity.CENTER_VERTICAL);
        return layout;
    }

    LinearLayout.LayoutParams size(int w, int h) {
        return new LinearLayout.LayoutParams(w < 0 ? w : dp(w), h < 0 ? h : dp(h));
    }

    void add(LinearLayout parent, View child, int top) {
        LinearLayout.LayoutParams lp = size(FILL, WRAP);
        lp.topMargin = dp(top);
        parent.addView(child, lp);
    }

    void rule(LinearLayout parent) {
        View divider = new View(activity);
        divider.setBackgroundColor(edge);
        parent.addView(divider, new LinearLayout.LayoutParams(FILL, Math.max(dp(1), 1)));
    }

    TextView label(String title, int sp, int tint, boolean medium) {
        TextView view = new TextView(activity);
        view.setText(title);
        view.setTextColor(tint);
        view.setTextSize(sp);
        view.setTypeface(
                Typeface.create(medium ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
        view.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        return view;
    }

    TextView heading(LinearLayout parent, String title, int top) {
        TextView view = label(title, 29, ink, true);
        view.setAccessibilityHeading(true);
        add(parent, view, top);
        return view;
    }

    GradientDrawable shape(int radius, int fill, int stroke) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(fill);
        shape.setCornerRadius(dp(radius));
        if (stroke != Color.TRANSPARENT) shape.setStroke(dp(1), stroke);
        return shape;
    }

    Drawable interactive(int radius, int fill, int stroke) {
        StateListDrawable background = new StateListDrawable();
        background.addState(
                STATES[0], shape(radius, color(R.color.disabled_surface), Color.TRANSPARENT));
        GradientDrawable focused = shape(radius, fill, primary);
        focused.setStroke(dp(2), primary);
        background.addState(new int[] {android.R.attr.state_focused}, focused);
        background.addState(STATES[1], shape(radius, fill, stroke));
        return new RippleDrawable(
                ColorStateList.valueOf((primary & 0x00ffffff) | 0x2b000000), background, null);
    }

    Drawable icon(int id, int tint, int dimension) {
        Drawable icon = activity.getDrawable(id).mutate();
        icon.setTint(tint);
        icon.setBounds(0, 0, dp(dimension), dp(dimension));
        return icon;
    }

    ImageView image(int id, int tint, int dimension) {
        ImageView image = new ImageView(activity);
        image.setImageDrawable(icon(id, tint, dimension));
        image.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        return image;
    }

    Button button(String text, Action style, View.OnClickListener listener) {
        Button b = new Button(activity);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextSize(16);
        b.setLetterSpacing(0);
        b.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        b.setMinimumHeight(dp(50));
        b.setMinHeight(dp(50));
        b.setMinWidth(0);
        b.setStateListAnimator(null);
        colors(b, style);
        pad(b, 12, 10, 12, 10);
        b.setOnClickListener(listener);
        return b;
    }

    void colors(Button b, Action style) {
        int fg =
                style == Action.FILLED
                        ? color(R.color.on_primary)
                        : style == Action.TONAL ? color(R.color.on_tonal) : ink;
        int bg = style == Action.FILLED ? primary : style == Action.TONAL ? tonal : surface;
        b.setTextColor(new ColorStateList(STATES, new int[] {color(R.color.disabled_ink), fg}));
        b.setBackground(interactive(12, bg, style == Action.OUTLINED ? edge : Color.TRANSPARENT));
    }

    Button iconButton(int drawable, String name, View.OnClickListener listener) {
        Button b = button("", Action.OUTLINED, listener);
        b.setMinimumHeight(dp(48));
        b.setMinHeight(dp(48));
        b.setContentDescription(name);
        b.setBackground(interactive(12, surface, Color.TRANSPARENT));
        Drawable icon = icon(drawable, ink, 24);
        b.setCompoundDrawablesRelative(icon, null, null, null);
        pad(b, 12, 0, 12, 0);
        return b;
    }

    void sideBySide(LinearLayout parent, Button first, Button second, int top) {
        LinearLayout row = row();
        row.setBaselineAligned(false);
        row.addView(first, new LinearLayout.LayoutParams(0, FILL, 1));
        LinearLayout.LayoutParams right = new LinearLayout.LayoutParams(0, FILL, 1);
        right.setMarginStart(dp(8));
        row.addView(second, right);
        add(parent, row, top);
    }
}
