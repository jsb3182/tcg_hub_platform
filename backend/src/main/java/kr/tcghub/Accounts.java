package kr.tcghub;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.Duration;
import java.util.*;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
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
    private static final String EMAIL_PATTERN = "[^@\\s]+@[^@\\s]+\\.[^@\\s]+";
    record Login(@NotBlank @Email @Size(max=254) String email, @NotBlank @Size(max=72) String password) {}
    record Registration(@NotBlank @Email @Size(max=254) @Pattern(regexp=EMAIL_PATTERN) String email,
                        String password) {
        Registration {
            if (email != null) email = email.strip().toLowerCase(Locale.ROOT);
        }
        @Override public String toString() { return "Registration[redacted]"; }
    }
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
        if (!email.matches(EMAIL_PATTERN) || email.length() > 254 ||
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
        if (createAccount(email, password, role).isEmpty()) throw new IllegalStateException("Account already exists");
        System.out.println("Account created.");
    }

    @Transactional
    public Session register(Registration request) {
        String password = request.password();
        // Keep password values out of validation errors and logs. BCrypt accepts at most 72 UTF-8 bytes.
        if (password == null || password.length() > 72 || password.isBlank()
                || password.codePointCount(0, password.length()) < 12 || tooLong(password))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        var user = createAccount(request.email(), password, "ROLE_USER")
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.CONFLICT));
        return newSession(user);
    }

    @Transactional
    public void initializeAdministrator(String email, String password) {
        // Serialize first start across replicas and public signup. Never adopt an existing user's password.
        db.sql("LOCK TABLE app_user IN SHARE ROW EXCLUSIVE MODE").update();
        if (db.sql("select exists(select from app_user where role='ROLE_ADMIN')").query(Boolean.class).single()) return;
        String normalized = email.strip().toLowerCase(Locale.ROOT);
        if (normalized.length() > 254 || !normalized.matches(EMAIL_PATTERN) || password.isBlank()
                || password.codePointCount(0, password.length()) < 12 || tooLong(password))
            throw new IllegalStateException("Check the bootstrap administrator email and password settings");
        if (createAccount(normalized, password, "ROLE_ADMIN").isEmpty())
            throw new IllegalStateException("The bootstrap email is already registered");
    }

    boolean activeAdministrator(String email) {
        return db.sql("select exists(select from app_user where email=? and enabled and role='ROLE_ADMIN')")
                .param(email).query(Boolean.class).single();
    }

    @Transactional
    public void changePassword(String email, String current, String next) {
        var account = db.sql("select * from app_user where email=? and enabled for update")
                .param(email.strip().toLowerCase(Locale.ROOT)).query(Account.class).optional().orElseThrow(Accounts::unauthorized);
        if (tooLong(current) || !passwords.matches(current, account.passwordHash())) throw unauthorized();
        if (next.isBlank() || next.equals(current) || next.codePointCount(0, next.length()) < 12 || tooLong(next))
            throw new IllegalArgumentException("Choose a different password of at least 12 characters and at most 72 UTF-8 bytes");
        db.sql("update app_user set password_hash=? where id=?").param(passwords.encode(next)).param(account.id()).update();
        db.sql("delete from refresh_session where user_id=?").param(account.id()).update();
        db.sql("delete from local_admin_session where user_id=?").param(account.id()).update();
    }

    private Optional<Account> createAccount(String email, String password, String role) {
        return db.sql("""
            insert into app_user(email,password_hash,role) values(?,?,?) on conflict(email) do nothing
            returning id,email,password_hash,role,enabled
            """).param(email).param(passwords.encode(password)).param(role).query(Account.class).optional();
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
