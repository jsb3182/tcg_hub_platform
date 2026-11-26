package kr.tcghub;

import java.io.Console;
import java.util.Arrays;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class HubApplication {
    public static void main(String[] args) {
        var app = new SpringApplication(HubApplication.class);
        if (Arrays.stream(args).anyMatch(arg -> arg.startsWith("--provision-account=") || arg.startsWith("--change-password="))) {
            app.setWebApplicationType(WebApplicationType.NONE);
            try (var context = app.run(args)) {
                var accounts = context.getBean(Accounts.class);
                String email = context.getEnvironment().getProperty("change-password");
                if (email == null) accounts.provision(context.getEnvironment());
                else {
                    changePasswordAtConsole(accounts, email);
                    System.out.println("Password changed.");
                }
            }
        } else {
            app.run(args);
        }
    }

    private static void changePasswordAtConsole(Accounts accounts, String email) {
        Console terminal = System.console();
        if (terminal == null) throw new IllegalStateException("Run the password change in an interactive terminal");
        char[] current = terminal.readPassword("Current password: ");
        char[] next = terminal.readPassword("New password: ");
        char[] confirm = terminal.readPassword("Repeat new password: ");
        try {
            if (current == null || next == null || !Arrays.equals(next, confirm))
                throw new IllegalArgumentException("New passwords do not match");
            // Use the transactional bean for all writes through the CLI entry point.
            accounts.changePassword(email, new String(current), new String(next));
        } finally {
            for (char[] value : new char[][]{current, next, confirm}) if (value != null) Arrays.fill(value, '\0');
        }
    }

}
