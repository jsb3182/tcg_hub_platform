package kr.tcghub;

import com.nimbusds.jose.jwk.RSAKey;
import java.net.ProxySelector;
import java.net.URI;
import java.net.UnixDomainSocketAddress;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.channels.Channels;
import java.nio.channels.ServerSocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import static java.net.StandardProtocolFamily.UNIX;
import static java.nio.charset.StandardCharsets.US_ASCII;
import static kr.tcghub.TestAccessProvider.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT, properties={
        "server.address=127.0.0.1", "tcg.public-origin=https://hub.example.invalid",
        "tcg.cf-team-domain=tcg-test-fixture.cloudflareaccess.com", "tcg.cf-audience=test-ops"})
@Import(TestAccessProvider.class)
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB", matches="1")
class HostLifecycleIntegrationTest {
    @TempDir static Path directory;
    @DynamicPropertySource
    static void socketProperty(DynamicPropertyRegistry properties) {
        properties.add("tcg.host-control-socket", () -> directory.resolve("ctl").toString());
    }

    @LocalServerPort int port;
    @Autowired RSAKey key;
    @Autowired JdbcClient db;
    @Autowired Tokens tokens;
    private final HttpClient http = HttpClient.newBuilder().proxy(ProxySelector.of(null))
            .connectTimeout(Duration.ofSeconds(3)).build();
    private long adminId;
    private String admin, access;

    @BeforeEach void operator() throws Exception {
        String email = UUID.randomUUID()+"@example.invalid";
        adminId = db.sql("insert into app_user(email,password_hash,role) values(?,'fixture','ROLE_ADMIN') returning id")
                .param(email).query(Long.class).single();
        admin = tokens.issue(email,"ROLE_ADMIN");
        access = assertion(key, ISSUER, "test-ops", Instant.now().plusSeconds(300));
    }

    @AfterEach void cleanup() throws Exception {
        Files.deleteIfExists(directory.resolve("ctl"));
        db.sql("delete from operator_action where user_id=?").param(adminId).update();
        db.sql("delete from app_user where id=?").param(adminId).update();
    }

    private int post(String command, String bearer, String assertion) throws Exception {
        URI url = URI.create("http://127.0.0.1:"+port+"/api/admin/server/"+command);
        var request = HttpRequest.newBuilder(url).timeout(Duration.ofSeconds(8))
                .header("Origin","https://hub.example.invalid").header("X-TCG-Request","1")
                .POST(HttpRequest.BodyPublishers.noBody());
        if (bearer != null) request.header("Authorization","Bearer "+bearer);
        if (assertion != null) request.header(ASSERTION,assertion);
        return http.send(request.build(), HttpResponse.BodyHandlers.discarding()).statusCode();
    }

    private List<String> audit() {
        return db.sql("select action from operator_action where user_id=? order by id")
                .param(adminId).query(String.class).list();
    }

    @ParameterizedTest
    @CsvSource({"restart,OK,202", "shutdown,OK,202", "restart,ERR,503"})
    void httpOutcomeDependsOnHostReply(String command, String reply, int expectedStatus) throws Exception {
        // The only host peer is this test. It records the protocol bytes and returns a fixed reply.
        try (var listener = ServerSocketChannel.open(UNIX)) {
            listener.bind(UnixDomainSocketAddress.of(directory.resolve("ctl")));
            var worker = Executors.newSingleThreadExecutor();
            byte[] expected = (command+"\n").getBytes(US_ASCII);
            try {
                var received = worker.submit(() -> {
                    try (var client = listener.accept()) {
                        var bytes = Channels.newInputStream(client).readNBytes(expected.length);
                        Channels.newOutputStream(client).write((reply+"\n").getBytes(US_ASCII));
                        return bytes;
                    }
                });
                assertEquals(expectedStatus, post(command, admin, access));
                assertArrayEquals(expected, received.get(5, TimeUnit.SECONDS));
            } finally {
                worker.shutdownNow();
            }
        }
        assertEquals(List.of("REQUEST_HOST_"+command.toUpperCase(Locale.ROOT)), audit());
    }

    @Test void unauthorizedRequestsNeverReachTheHost() throws Exception {
        try (var listener = ServerSocketChannel.open(UNIX)) {
            listener.bind(UnixDomainSocketAddress.of(directory.resolve("ctl")));
            assertEquals(401, post("restart", null, access));
            assertEquals(403, post("shutdown", admin, null));
            assertEquals(403, post("restart", tokens.issue("member@example.invalid","ROLE_USER"), access));
            listener.configureBlocking(false);
            try (var unexpected = listener.accept()) {
                assertNull(unexpected);
            }
        }
        assertEquals(List.of(), audit());
    }
}
