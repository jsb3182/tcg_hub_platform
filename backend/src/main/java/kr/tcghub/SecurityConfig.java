package kr.tcghub;

import java.util.List;
import jakarta.servlet.DispatcherType;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.*;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
@ConditionalOnWebApplication(type=ConditionalOnWebApplication.Type.SERVLET)
class SecurityConfig {
    @Bean
    SecurityFilterChain api(HttpSecurity http, Tokens tokens, AccessGate access,
                            @Value("${tcg.public-origin}") String origin) throws Exception {
        http.sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(c -> c.disable()).logout(c -> c.disable()).csrf(c -> c.disable())
            .headers(h -> h.contentSecurityPolicy(c -> c.policyDirectives(
                    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")))
            .oauth2ResourceServer(o -> o.jwt(j -> j.decoder(tokens.decoder).jwtAuthenticationConverter(jwt ->
                    new JwtAuthenticationToken(jwt, List.of(new SimpleGrantedAuthority(jwt.getClaimAsString("role")))))))
            .authorizeHttpRequests(a -> a
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/admin","/admin/**").access((auth, ctx) ->
                        new AuthorizationDecision(access.admits(ctx.getRequest())))
                .requestMatchers("/api/v1/admin","/api/v1/admin/**").access((auth,ctx) ->
                        new AuthorizationDecision(auth.get().getAuthorities().contains(new SimpleGrantedAuthority("ROLE_ADMIN"))
                                && access.admits(ctx.getRequest())))
                .requestMatchers(HttpMethod.POST,"/api/v1/auth/login","/api/v1/auth/refresh","/api/v1/auth/logout").permitAll()
                .requestMatchers(HttpMethod.GET,"/api/v1/games","/api/v1/packs","/api/v1/cards","/api/v1/cards/*").permitAll()
                .requestMatchers("/api/**").denyAll()
                .requestMatchers("/internal/ready").access((auth,ctx) -> {
                    var request = ctx.getRequest();
                    return new AuthorizationDecision("127.0.0.1".equals(request.getRemoteAddr())
                            && request.getHeader("CF-Ray")==null && request.getHeader("CF-Connecting-IP")==null);
                })
                .requestMatchers(HttpMethod.GET,"/**").permitAll()
                .requestMatchers(HttpMethod.HEAD,"/**").permitAll()
                .anyRequest().denyAll())
            .addFilterBefore(new ApiGuard(origin), AuthorizationFilter.class);
        return http.build();
    }
}
