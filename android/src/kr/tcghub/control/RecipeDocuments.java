package kr.tcghub.control;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.util.Base64;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import java.io.*;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

/** Image inputs and user-selected PNG output. No storage permission or JavaScript interface. */
final class RecipeDocuments {
    private static final int PICK=91, SAVE=92, MAX=16*1024*1024;
    private final Activity activity;
    private final WebView web;
    private final PlatformOrigin origin;
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private ValueCallback<Uri[]> selected;
    private String token;
    private File staged;
    private int bytes;
    private boolean closed;

    RecipeDocuments(Activity activity,WebView web,PlatformOrigin origin) {
        this.activity=activity; this.web=web; this.origin=origin;
        web.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onShowFileChooser(WebView view,ValueCallback<Uri[]> cb,FileChooserParams params) {
                if(selected!=null) {selected.onReceiveValue(null);selected=null;}
                if(!trusted() || params.getMode()!=FileChooserParams.MODE_OPEN) {cb.onReceiveValue(null);return true;}
                selected=cb;
                Intent pick=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE);
                pick.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/png","image/jpeg","image/webp"});
                try {activity.startActivityForResult(pick,PICK);} catch(RuntimeException e){selected=null;cb.onReceiveValue(null);}
                return true;
            }
        });
    }
    private boolean trusted(){String url=web.getUrl();return !closed && url!=null && origin.owns(url);}
    private void notifyPage(String key,boolean ok){
        if(trusted())web.evaluateJavascript("window.__tcgPngDone && window.__tcgPngDone("+JSONObject.quote(key)+","+ok+")",null);
    }
    private void finish(String key,boolean ok){
        if(!key.equals(token))return;
        if(staged!=null)staged.delete();
        staged=null;token=null;notifyPage(key,ok);
    }
    boolean export(Uri uri) {
        if(!"tcghub-save".equals(uri.getScheme()))return false;
        String kind=uri.getHost();
        if(!trusted() || !("png".equals(kind)||"json".equals(kind)||"xlsx".equals(kind)||"ics".equals(kind)) || uri.getPathSegments().size()!=1)return true;
        String key=uri.getLastPathSegment();
        if(key==null || !key.matches("[a-f0-9]{32}"))return true;
        int size;
        try {size=Integer.parseInt(uri.getQueryParameter("size"));}catch(RuntimeException ex){size=0;}
        if(token!=null || size<24 || size>MAX){notifyPage(key,false);return true;}
        String name=uri.getQueryParameter("name");
        if(name==null || name.length()>100 || name.contains("/") || name.contains("\\") || !name.endsWith("."+kind))name="TCG."+kind;
        try{staged=File.createTempFile("recipe-","."+kind,activity.getCacheDir());}
        catch(IOException ex){notifyPage(key,false);return true;}
        token=key;bytes=size;read(key,name,kind,0);
        return true;
    }
    private void read(String key,String name,String kind,int offset) {
        if(!key.equals(token))return;
        if(!trusted()){finish(key,false);return;}
        web.evaluateJavascript("window.__tcgPngRead && window.__tcgPngRead("+JSONObject.quote(key)+","+offset+")", result->{
            if(!key.equals(token)||closed)return;
            File file=staged;
            io.execute(()->{
                try {
                    if(result==null || result.length()<6 || result.length()>49154 || result.charAt(0)!='"')throw new IOException();
                    String part=result.substring(1,result.length()-1);
                    byte[] chunk=Base64.decode(part,Base64.NO_WRAP);
                    long before=file.length(),after=before+chunk.length;
                    if(before!=(long)offset/4*3 || after>bytes || chunk.length==0)throw new IOException();
                    if(before==0 && !matches(kind,chunk))throw new IOException();
                    try(FileOutputStream out=new FileOutputStream(file,true)){out.write(chunk);}
                    activity.runOnUiThread(()->{
                        if(!key.equals(token)||closed)return;
                        if(after==bytes) chooseDestination(key,name,kind);
                        else read(key,name,kind,offset+part.length());
                    });
                }catch(Exception ex){activity.runOnUiThread(()->finish(key,false));}
            });
        });
    }
    private void chooseDestination(String key,String name,String kind) {
        if(!trusted()){finish(key,false);return;}
        if(!kind.equals("png") || Build.VERSION.SDK_INT<29){chooseFolder(key,name,kind);return;}
        new AlertDialog.Builder(activity).setTitle(R.string.save_png_title)
                .setItems(new String[]{activity.getString(R.string.save_gallery),activity.getString(R.string.save_folder)},
                        (dialog,which)->{
                            if(!key.equals(token) || !trusted()){finish(key,false);return;}
                            if(which==1){chooseFolder(key,name,kind);return;}
                            File file=staged;
                            io.execute(()->{
                                try {
                                    GalleryPng.publish(activity.getContentResolver(),file,name);
                                    activity.runOnUiThread(()->finish(key,true));
                                } catch(IOException | RuntimeException ex){activity.runOnUiThread(()->finish(key,false));}
                            });
                        })
                .setNegativeButton(R.string.cancel,(dialog,which)->finish(key,false))
                .setOnCancelListener(dialog->finish(key,false)).show();
    }
    private void chooseFolder(String key,String name,String kind) {
        String mime=kind.equals("png")?"image/png":kind.equals("json")?"application/json":kind.equals("ics")?"text/calendar":
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
        try {activity.startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).setType(mime)
                .addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,name),SAVE);}
        catch(RuntimeException ex){finish(key,false);}
    }
    private static boolean matches(String kind,byte[] chunk) {
        if(chunk.length<4)return false;
        if(kind.equals("json"))return chunk[0]=='{';
        if(kind.equals("ics"))return chunk.length>=17 && new String(chunk,0,17,java.nio.charset.StandardCharsets.US_ASCII).equals("BEGIN:VCALENDAR\r\n");
        if(kind.equals("xlsx"))return chunk[0]==80 && chunk[1]==75 && chunk[2]==3 && chunk[3]==4;
        return chunk.length>=24 && chunk[0]==(byte)137 && chunk[1]==80 && chunk[2]==78 && chunk[3]==71
                && chunk[4]==13 && chunk[5]==10 && chunk[6]==26 && chunk[7]==10;
    }
    boolean result(int request,int result,Intent data) {
        if(request!=PICK && request!=SAVE)return false;
        Uri uri=result==Activity.RESULT_OK && data!=null?data.getData():null;
        if(uri!=null && !"content".equals(uri.getScheme()))uri=null;
        if(request==PICK) {
            ValueCallback<Uri[]> cb=selected;selected=null;
            if(cb!=null) {
                String type=null;
                try{if(uri!=null)type=activity.getContentResolver().getType(uri);}catch(RuntimeException ignored){}
                boolean image=type!=null && type.toLowerCase(Locale.ROOT).matches("image/(png|jpeg|webp)");
                cb.onReceiveValue(image && trusted()?new Uri[]{uri}:null);
            }
            return true;
        }
        String key=token;
        if(key==null)return true;
        if(uri==null || !trusted()){finish(key,false);return true;}
        Uri target=uri;File src=staged;
        io.execute(()->{
            try { GalleryPng.copy(activity.getContentResolver(),src,target); }
            catch(Exception ex){activity.runOnUiThread(()->finish(key,false));return;}
            activity.runOnUiThread(()->finish(key,true));
        });
        return true;
    }
    void close(){
        closed=true;
        if(selected!=null)selected.onReceiveValue(null);
        selected=null;token=null;if(staged!=null)staged.delete();io.shutdownNow();
    }
}
