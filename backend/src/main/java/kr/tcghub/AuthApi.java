package kr.tcghub;

import java.security.Principal;
import java.time.Duration;
import java.util.Map;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
class AuthApi {
    private static final String COOKIE = "__Secure-tcg_refresh";
    private final Accounts accounts;
    AuthApi(Accounts accounts) { this.accounts = accounts; }

    @PostMapping("/auth/login")
    Accounts.Access login(@Valid @RequestBody Accounts.Login login, HttpServletResponse response) {
        return setSession(accounts.login(login), response);
    }

    @PostMapping("/auth/refresh")
    Accounts.Access refresh(@CookieValue(value=COOKIE, required=false) String refresh, HttpServletResponse response) {
        return setSession(accounts.rotate(refresh), response);
    }

    @PostMapping("/auth/logout")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void logout(@CookieValue(value=COOKIE, required=false) String refresh, HttpServletResponse response) {
        accounts.revoke(refresh);
        cookie(response, "", Duration.ZERO);
    }

    @GetMapping("/admin/status")
    Map<String,String> status(Principal user) { return Map.of("status","UP","user",user.getName()); }

    private Accounts.Access setSession(Accounts.Session session, HttpServletResponse response) {
        cookie(response, session.refresh(), Accounts.REFRESH_LIFETIME);
        return session.access();
    }

    private static void cookie(HttpServletResponse response, String token, Duration age) {
        response.addHeader(HttpHeaders.SET_COOKIE, ResponseCookie.from(COOKIE,token).httpOnly(true).secure(true)
                .sameSite("Strict").path("/api/v1/auth").maxAge(age).build().toString());
    }
}
