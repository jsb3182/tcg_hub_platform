package kr.tcghub;

import java.io.IOException;
import java.util.Set;
import java.util.regex.Pattern;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.*;
import org.springframework.web.filter.OncePerRequestFilter;

/** Move a local browser document before it prompts for credentials. API writes keep their original guard. */
final class LocalEntryRedirect extends OncePerRequestFilter {
    private static final Pattern PRIVATE_PAGE = Pattern.compile("/(?:login|binder|decks(?:/new|/[0-9]+)?)/?");
    private final LocalAdmin local;
    LocalEntryRedirect(LocalAdmin local) { this.local=local; }

    @Override protected void doFilterInternal(HttpServletRequest request,HttpServletResponse response,FilterChain chain)
            throws IOException,ServletException {
        String path=request.getRequestURI();
        boolean admin=path.equals("/admin") || path.startsWith("/admin/");
        boolean practice=path.equals("/play") && request.getParameter("deck")!=null;
        if (Set.of("GET","HEAD").contains(request.getMethod()) && (admin || practice || PRIVATE_PAGE.matcher(path).matches())
                && local.localEntryAlias(request)) {
            // The authority is constant and the path has matched a registered application document.
            // A login's optional next parameter is validated by LoginView and never selects an HTTP destination here.
            String query=request.getQueryString();
            String target=admin ? "/login?next=/admin" : path + (query==null ? "" : "?"+query);
            response.setStatus(HttpServletResponse.SC_FOUND);
            response.setHeader("Location",LocalAdmin.LOCAL_ORIGIN+target);
            response.setHeader("Cache-Control","no-store");
            response.setHeader("Referrer-Policy","no-referrer");
            return;
        }
        chain.doFilter(request,response);
    }
}
