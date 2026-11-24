package kr.tcghub;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.Duration;
import java.util.*;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
class Accounts {
    record Login(@NotBlank @Email @Size(max=254) String email, @NotBlank @Size(max=72) String password) {}
    record Account(long id, String email, String passwordHash, String role, boolean enabled) {}
    record Access(String accessToken, String role, String email) {}
    record Session(Access access, String refresh) {}
    static final Duration REFRESH_LIFETIME = Duration.ofDays(14);
    private final BCryptPasswordEncoder passwords = new BCryptPasswordEncoder();
    private final String dummyHash = passwords.encode(UUID.randomUUID().toString());
    private static final SecureRandom RANDOM = new SecureRandom();
    private final JdbcClient db;
    private final Tokens tokens;

    Accounts(JdbcClient db, Tokens tokens) {
        this.db = db;
        this.tokens = tokens;
    }

    void provision(Environment environment) {
        String email = environment.getRequiredProperty("provision-account").strip().toLowerCase(Locale.ROOT);
        String role = environment.getProperty("account-role", "ROLE_USER");
        if (!email.matches("[^@\\s]+@[^@\\s]+\\.[^@\\s]+") || email.length() > 254 ||
                !Set.of("ROLE_USER","ROLE_ADMIN").contains(role)) {
            throw new IllegalArgumentException("Provide a valid email and ROLE_USER or ROLE_ADMIN");
        }
        String password;
        try {
            Console console = System.console();
            password = console == null ? new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8)).readLine()
                    : new String(console.readPassword("Password: "));
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
        if (password == null || password.length() < 12 || tooLong(password)) {
            throw new IllegalArgumentException("Use at least 12 characters and at most 72 UTF-8 bytes");
        }
        int created = db.sql("""
            insert into app_user(email,password_hash,role) values(?,?,?) on conflict(email) do nothing
            """).param(email).param(passwords.encode(password)).param(role).update();
        if (created == 0) throw new IllegalStateException("Account already exists");
        System.out.println("Account created.");
    }

    @Transactional
    public Session login(Login request) {
        var account = db.sql("select * from app_user where email=?").param(request.email().strip().toLowerCase(Locale.ROOT))
                .query(Account.class).optional();
        boolean matches = !tooLong(request.password()) && passwords.matches(request.password(),
                account.map(Account::passwordHash).orElse(dummyHash));
        return newSession(account.filter(user -> matches && user.enabled()).orElseThrow(Accounts::unauthorized));
    }

    @Transactional
    public Session rotate(String refresh) {
        var userId = db.sql("""
            update refresh_session set revoked_at=now()
            where token_hash=? and revoked_at is null and expires_at>now() returning user_id
            """).param(hash(refresh)).query(Long.class).optional().orElseThrow(Accounts::unauthorized);
        var account = db.sql("select * from app_user where id=? and enabled")
                .param(userId).query(Account.class).optional().orElseThrow(Accounts::unauthorized);
        return newSession(account);
    }

    void revoke(String refresh) {
        if (refresh != null && refresh.length() == 43)
            db.sql("update refresh_session set revoked_at=now() where token_hash=? and revoked_at is null")
                    .param(hash(refresh)).update();
    }

    private Session newSession(Account user) {
        String refresh = randomToken();
        db.sql("delete from refresh_session where expires_at<=now()").update();
        db.sql("insert into refresh_session(user_id,token_hash,expires_at) values(?,?,now() + (? * interval '1 second'))")
                .param(user.id()).param(hash(refresh)).param(REFRESH_LIFETIME.toSeconds()).update();
        return new Session(new Access(tokens.issue(user.email(), user.role()), user.role(), user.email()), refresh);
    }

    private static boolean tooLong(String value) {
        return value.getBytes(StandardCharsets.UTF_8).length > 72;
    }

    static String randomToken() {
        byte[] entropy = new byte[32];
        RANDOM.nextBytes(entropy);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(entropy);
    }

    static String hash(String token) {
        if (token == null || token.length() != 43) throw unauthorized();
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(token.getBytes(StandardCharsets.US_ASCII)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static ResponseStatusException unauthorized() {
        return new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }
}
