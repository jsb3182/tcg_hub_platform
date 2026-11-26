package kr.tcghub.control;

import android.content.ContentResolver;
import android.content.Intent;
import android.content.UriPermission;
import android.net.Uri;
import android.provider.DocumentsContract;

final class ControlFolder {
    static final String AUTHORITY = "com.termux.documents";
    static final String ID = "/data/data/com.termux/files/home/tcg-control";
    static final int FLAGS = Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION;

    private ControlFolder() {}

    static boolean matches(Uri uri) {
        return uri != null && "content".equals(uri.getScheme()) && AUTHORITY.equals(uri.getAuthority())
                && uri.getQuery() == null && uri.getFragment() == null
                && uri.getPathSegments().size() == 2 && DocumentsContract.isTreeUri(uri)
                && ID.equals(DocumentsContract.getTreeDocumentId(uri));
    }

    static Uri paired(ContentResolver resolver, String saved) {
        if (saved.isEmpty()) return null;
        Uri tree = Uri.parse(saved);
        if (!matches(tree)) return null;
        for (UriPermission grant : resolver.getPersistedUriPermissions()) {
            if (tree.equals(grant.getUri()) && grant.isReadPermission() && grant.isWritePermission()) return tree;
        }
        return null;
    }
}
