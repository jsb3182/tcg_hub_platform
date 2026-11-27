package kr.tcghub;

import java.util.List;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.*;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
@ConditionalOnWebApplication(type=ConditionalOnWebApplication.Type.SERVLET)
class SecurityConfig {
    @Bean
    SecurityFilterChain api(HttpSecurity http, Tokens tokens, LocalAdmin local, Accounts accounts, MapConfiguration map,
                            @Value("${tcg.public-origin}") String origin) throws Exception {
        http.sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(c -> c.disable()).logout(c -> c.disable()).csrf(c -> c.disable())
            .headers(h -> h.contentSecurityPolicy(c -> c.policyDirectives(map.contentPolicy())))
            .oauth2ResourceServer(o -> o.jwt(j -> j.decoder(tokens.decoder).jwtAuthenticationConverter(jwt ->
                    new JwtAuthenticationToken(jwt, List.of(new SimpleGrantedAuthority(jwt.getClaimAsString("role")))))))
            .exceptionHandling(e -> e.authenticationEntryPoint((req,res,error) -> {
                if (!redirectLocalLogin(local,req,res)) new BearerTokenAuthenticationEntryPoint().commence(req,res,error);
            }).accessDeniedHandler((req,res,error) -> {
                if (!redirectLocalLogin(local,req,res)) new BearerTokenAccessDeniedHandler().handle(req,res,error);
            }))
            .authorizeHttpRequests(a -> a
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/admin","/admin/**").access((auth, ctx) ->
                        new AuthorizationDecision(local.admits(ctx.getRequest(), null)))
                .requestMatchers("/api/v1/admin","/api/v1/admin/**","/api/admin/server/**").access((auth,ctx) ->
                        new AuthorizationDecision(auth.get().getAuthorities().contains(new SimpleGrantedAuthority("ROLE_ADMIN"))
                                && local.admits(ctx.getRequest(),auth.get().getName())
                                && accounts.activeAdministrator(auth.get().getName())))
                .requestMatchers(HttpMethod.POST,"/api/v1/auth/local-admin").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET,"/api/v1/auth/admin-mode").permitAll()
                .requestMatchers(HttpMethod.POST,"/api/v1/auth/register","/api/v1/auth/login","/api/v1/auth/refresh","/api/v1/auth/logout").permitAll()
                .requestMatchers(HttpMethod.GET,"/api/v1/games","/api/v1/packs","/api/v1/packs/*","/api/v1/catalog-packs","/api/v1/releases","/api/v1/release-calendar","/api/v1/cards","/api/v1/cards/*",
                        "/api/v1/news","/api/v1/stores","/api/v1/config","/api/v1/shared/decks/*","/api/v1/play/cards").permitAll()
                .requestMatchers("/api/v1/me/**","/api/decks/import-capture").authenticated()
                .requestMatchers("/api/**").denyAll()
                .requestMatchers("/internal/ready").access((auth,ctx) -> {
                    var request = ctx.getRequest();
                    return new AuthorizationDecision("127.0.0.1".equals(request.getRemoteAddr())
                            && request.getHeader("CF-Ray")==null && request.getHeader("CF-Connecting-IP")==null);
                })
                .requestMatchers(HttpMethod.GET,"/**").permitAll()
                .requestMatchers(HttpMethod.HEAD,"/**").permitAll()
                .anyRequest().denyAll())
            .addFilterBefore(new LocalEntryRedirect(local), AuthorizationFilter.class)
            .addFilterBefore(new ApiGuard(origin), AuthorizationFilter.class);
        return http.build();
    }

    private boolean redirectLocalLogin(LocalAdmin local, HttpServletRequest req, HttpServletResponse res) {
        String path = req.getRequestURI();
        if (!(req.getMethod().equals("GET") || req.getMethod().equals("HEAD"))
                || !(path.equals("/admin") || path.startsWith("/admin/"))
                || local.mode(req) != LocalAdmin.Mode.LOCAL_TOTP) return false;
        res.setStatus(HttpServletResponse.SC_FOUND);
        res.setHeader("Location","/login?next=/admin");
        res.setHeader("Cache-Control","no-store");
        return true;
    }
}
