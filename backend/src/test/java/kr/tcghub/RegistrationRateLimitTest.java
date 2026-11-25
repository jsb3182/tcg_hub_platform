package kr.tcghub;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import static org.junit.jupiter.api.Assertions.*;

class RegistrationRateLimitTest {
    private static final String ORIGIN = "https://example.invalid";
    private final ApiGuard guard = new ApiGuard(ORIGIN);

    private MockHttpServletResponse post(String path, String ip) throws Exception {
        var request = new MockHttpServletRequest("POST", path);
        request.setServletPath(path);
        request.setRemoteAddr(ip);
        request.addHeader("Origin", ORIGIN);
        request.addHeader("X-TCG-Request", "1");
        var response = new MockHttpServletResponse();
        guard.doFilter(request, response, (req, res) -> response.setStatus(204));
        return response;
    }

    @Test void signupLimitIsSeparateFromLoginAndHasAnOverallBudget() throws Exception {
        String register = "/api/v1/auth/register";
        for (int i = 0; i < 5; i++) assertEquals(204, post(register, "192.0.2.1").getStatus());
        var limited = post(register, "192.0.2.1");
        assertEquals(429, limited.getStatus());
        assertTrue(Integer.parseInt(limited.getHeader("Retry-After")) > 0);
        for (int i = 2; i <= 8; i++) assertEquals(204, post(register, "192.0.2." + i).getStatus());
        var global = post(register, "192.0.2.9");
        assertEquals(429, global.getStatus());
        assertTrue(Integer.parseInt(global.getHeader("Retry-After")) > 0);
        assertEquals(204, post("/api/v1/auth/login", "192.0.2.1").getStatus());
    }
}
