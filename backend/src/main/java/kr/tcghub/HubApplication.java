package kr.tcghub;

import java.util.Arrays;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HubApplication {
    public static void main(String[] args) {
        var app = new SpringApplication(HubApplication.class);
        if (Arrays.stream(args).anyMatch(arg -> arg.startsWith("--provision-account="))) {
            app.setWebApplicationType(WebApplicationType.NONE);
            try (var context = app.run(args)) {
                context.getBean(Accounts.class).provision(context.getEnvironment());
            }
        } else {
            app.run(args);
        }
    }
}
