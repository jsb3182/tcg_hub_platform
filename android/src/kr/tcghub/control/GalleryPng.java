package kr.tcghub.control;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Environment;
import android.provider.MediaStore;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/** Publish one user-confirmed PNG to scoped storage (API 29+). */
final class GalleryPng {
    static Uri publish(ContentResolver resolver, File file, String name) throws IOException {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeFile(file.getPath(), bounds);
        if (!"image/png".equals(bounds.outMimeType) || bounds.outWidth <= 0 || bounds.outHeight <= 0)
            throw new IOException("Invalid PNG");
        ContentValues values = new ContentValues();
        values.put(MediaStore.Images.Media.DISPLAY_NAME, name);
        values.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
        values.put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/TCG Hub/");
        values.put(MediaStore.Images.Media.IS_PENDING, 1);
        Uri target = resolver.insert(MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY), values);
        if (target == null) throw new IOException("Gallery entry unavailable");
        boolean published = false;
        try {
            copy(resolver, file, target);
            values.clear();
            values.put(MediaStore.Images.Media.IS_PENDING, 0);
            if (resolver.update(target, values, null, null) != 1) throw new IOException("Could not publish image");
            published = true;
            return target;
        } finally {
            if (!published) resolver.delete(target, null, null);
        }
    }

    static void copy(ContentResolver resolver, File file, Uri target) throws IOException {
        try (InputStream in = new FileInputStream(file); OutputStream out = resolver.openOutputStream(target,"wt")) {
            if (out == null) throw new IOException("Missing output stream");
            byte[] buffer = new byte[16384];
            int count;
            while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
        }
    }

    private GalleryPng() {}
}
