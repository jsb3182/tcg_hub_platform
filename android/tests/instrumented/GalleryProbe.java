package kr.tcghub.control;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Intent;
import android.content.IntentFilter;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.net.Uri;
import android.os.Bundle;
import android.os.SystemClock;
import android.provider.MediaStore;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import java.io.ByteArrayOutputStream;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Android instrumentation fixture. Uses its own activity, WebView and one disposable PNG. */
public final class GalleryProbe extends Instrumentation {
    public static final class Page extends Activity {
        final CountDownLatch loaded = new CountDownLatch(1);
        WebView web;
        RecipeDocuments documents;

        @Override public void onCreate(Bundle state) {
            super.onCreate(state);
            web = new WebView(this);
            setContentView(web);
            web.getSettings().setJavaScriptEnabled(true);
            documents = new RecipeDocuments(this, web, new PlatformOrigin(PlatformOrigin.LOCAL));
            web.setWebViewClient(new WebViewClient() {
                @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                    return new WebResourceResponse("text/html", "UTF-8", new ByteArrayInputStream(
                            "<!doctype html><title>Gallery test</title>".getBytes(java.nio.charset.StandardCharsets.UTF_8)));
                }
                @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                    return request.isForMainFrame() && documents.export(request.getUrl());
                }
                @Override public void onPageFinished(WebView view, String url) { loaded.countDown(); }
            });
            web.loadUrl(PlatformOrigin.LOCAL);
        }

        @Override protected void onActivityResult(int request, int result, Intent data) {
            if (!documents.result(request, result, data)) super.onActivityResult(request, result, data);
        }

        @Override protected void onDestroy() {
            documents.close();
            web.destroy();
            super.onDestroy();
        }
    }

    @Override public void onCreate(Bundle arguments) { super.onCreate(arguments); start(); }
    private static void check(boolean ok, String reason) { if (!ok) throw new AssertionError(reason); }

    private String js(Page page, String code) throws InterruptedException {
        AtomicReference<String> response = new AtomicReference<>();
        CountDownLatch completed = new CountDownLatch(1);
        runOnMainSync(() -> page.web.evaluateJavascript(code, result -> {response.set(result); completed.countDown();}));
        check(completed.await(5, TimeUnit.SECONDS), "JavaScript callback timed out");
        return response.get();
    }

    private void awaitJs(Page page, String expected) throws Exception {
        long limit = SystemClock.elapsedRealtime() + 5000;
        do {
            if (expected.equals(js(page, "window.completed"))) return;
            SystemClock.sleep(100);
        } while (SystemClock.elapsedRealtime() < limit);
        throw new AssertionError("Export callback did not report " + expected);
    }

    private void press(String text) {
        long limit = SystemClock.elapsedRealtime() + 10000;
        String visible = "";
        do {
            AccessibilityNodeInfo root = getUiAutomation().getRootInActiveWindow();
            if (root != null) {
                visible=String.valueOf(root.getPackageName())+" "+root.getChildCount();
                List<AccessibilityNodeInfo> found = root.findAccessibilityNodeInfosByText(text);
                for (AccessibilityNodeInfo match : found) {
                    if (!text.contentEquals(match.getText())) continue;
                    for (AccessibilityNodeInfo n = match; n != null; n = n.getParent()) {
                        if (n.isClickable() && n.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return;
                    }
                    Rect rect=new Rect();
                    match.getBoundsInScreen(rect);
                    if (!rect.isEmpty()) {
                        long now=SystemClock.uptimeMillis();
                        for (int action:new int[]{MotionEvent.ACTION_DOWN,MotionEvent.ACTION_UP}) {
                            MotionEvent touch=MotionEvent.obtain(now,SystemClock.uptimeMillis(),action,rect.centerX(),rect.centerY(),0);
                            touch.setSource(InputDevice.SOURCE_TOUCHSCREEN);
                            getUiAutomation().injectInputEvent(touch,true);
                            touch.recycle();
                        }
                        return;
                    }
                }
            }
            SystemClock.sleep(100);
        } while (SystemClock.elapsedRealtime() < limit);
        throw new AssertionError("Missing dialog choice: " + text+"; active "+visible);
    }

    private void export(Page page, byte[] data, String displayName, String kind) throws Exception {
        String base64 = android.util.Base64.encodeToString(data, android.util.Base64.NO_WRAP);
        String command = "tcghub-save://"+kind+"/00112233445566778899aabbccddeeff?name=" + displayName + "&size=" + data.length;
        js(page, "window.completed=null;window.__tcgPngDone=(k,ok)=>window.completed=ok;" +
                "window.__tcgPngRead=(k,o)=>'" + base64 + "'.slice(o,o+49152);location.assign('" + command + "');");
    }

    @Override public void onStart() {
        Bundle result = new Bundle();
        Uri owned = null;
        Uri calendarFile = null;
        try {
            Page page = (Page) startActivitySync(new Intent(getTargetContext(), Page.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            check(page.loaded.await(10, TimeUnit.SECONDS), "WebView did not load");
            Bitmap bitmap = Bitmap.createBitmap(3, 2, Bitmap.Config.ARGB_8888);
            bitmap.eraseColor(0xff5b3fd0);
            ByteArrayOutputStream encoded = new ByteArrayOutputStream();
            check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, encoded), "PNG encoding failed");
            bitmap.recycle();
            byte[] png = encoded.toByteArray();
            String displayName = "TCG-gallery-qa-" + SystemClock.elapsedRealtime() + ".png";
            export(page, png, displayName, "png");
            press(page.getString(R.string.save_gallery));
            awaitJs(page, "true");
            Uri images = MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY);
            try (Cursor row = page.getContentResolver().query(images,
                    new String[]{"_id","relative_path","is_pending","mime_type"}, "_display_name=?", new String[]{displayName}, null)) {
                check(row != null && row.moveToFirst(), "Published PNG missing");
                owned = ContentUris.withAppendedId(images, row.getLong(0));
                check("Pictures/TCG Hub/".equals(row.getString(1)) && row.getInt(2)==0 && "image/png".equals(row.getString(3)), "Gallery metadata mismatch");
                check(!row.moveToNext(), "Duplicate gallery entry");
            }
            try (InputStream in = page.getContentResolver().openInputStream(owned)) {
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                byte[] block = new byte[4096]; int read;
                while ((read = in.read(block)) != -1) bytes.write(block,0,read);
                check(Arrays.equals(png,bytes.toByteArray()), "Gallery PNG bytes differ");
            }
            IntentFilter filter = new IntentFilter(Intent.ACTION_CREATE_DOCUMENT);
            filter.addDataType("image/png"); filter.addCategory(Intent.CATEGORY_OPENABLE);
            ActivityMonitor picker = addMonitor(filter, new ActivityResult(Activity.RESULT_CANCELED,null), true);
            try {
                export(page, png, displayName, "png");
                press(page.getString(R.string.save_folder));
                awaitJs(page, "false");
                check(picker.getHits()==1, "Folder choice did not open document picker");
            } finally { removeMonitor(picker); }
            byte[] calendar=("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//TCG QA//EN\r\n"
                    +"BEGIN:VEVENT\r\nUID:1@fixture\r\nDTSTAMP:20270101T120000Z\r\nDTSTART:20270301T100000Z\r\n"
                    +"SUMMARY:테스트\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:테스트\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\n"
                    +"END:VEVENT\r\nEND:VCALENDAR\r\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
            ContentValues values=new ContentValues();
            values.put(MediaStore.Downloads.DISPLAY_NAME,displayName+".ics");
            values.put(MediaStore.Downloads.MIME_TYPE,"text/calendar");
            values.put(MediaStore.Downloads.IS_PENDING,1);
            calendarFile=page.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values);
            check(calendarFile!=null,"Missing fixture output URI");
            IntentFilter calendarPicker=new IntentFilter(Intent.ACTION_CREATE_DOCUMENT);
            calendarPicker.addDataType("text/calendar"); calendarPicker.addCategory(Intent.CATEGORY_OPENABLE);
            ActivityMonitor fileChoice=addMonitor(calendarPicker,new ActivityResult(Activity.RESULT_OK,new Intent().setData(calendarFile)),true);
            try {
                export(page,calendar,"TCG-event.ics","ics");
                awaitJs(page,"true");
                check(fileChoice.getHits()==1,"ICS picker did not request text/calendar");
                try (InputStream in=page.getContentResolver().openInputStream(calendarFile)) {
                    for (byte b:calendar) check(in.read()==(b&255),"Unexpected calendar data");
                    check(in.read()==-1,"Unexpected trailing calendar data");
                }
            } finally { removeMonitor(fileChoice); }
            runOnMainSync(page::finish);
            result.putString("proof","webview_export=true,gallery_bytes="+png.length+",gallery_pending=0,folder_picker=1,cancel_callback=true,calendar_picker=1,calendar_bytes="+calendar.length);
            finish(Activity.RESULT_OK, result);
        } catch (Throwable failure) {
            result.putString("failure",android.util.Log.getStackTraceString(failure));
            finish(Activity.RESULT_CANCELED, result);
        } finally {
            if (owned != null) getTargetContext().getContentResolver().delete(owned,null,null);
            if (calendarFile != null) getTargetContext().getContentResolver().delete(calendarFile,null,null);
        }
    }
}
