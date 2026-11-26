package kr.tcghub;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnWebApplication
class DataInitializer implements ApplicationRunner {
    private final Accounts accounts;
    private final Environment settings;

    DataInitializer(Accounts accounts, Environment settings) {
        this.accounts = accounts;
        this.settings = settings;
    }

    @Override public void run(ApplicationArguments args) {
        String email = settings.getProperty("tcg.bootstrap.email", "");
        String password = settings.getProperty("tcg.bootstrap.password", "");
        if (!email.isEmpty() || !password.isEmpty()) accounts.initializeAdministrator(email, password);
    }
}
