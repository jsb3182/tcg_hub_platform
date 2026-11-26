package kr.tcghub;

import java.security.Principal;
import java.time.OffsetDateTime;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin/server")
class ServerApi {
    record Status(String database, boolean schedulerEnabled, boolean crawlerEnabled, boolean hostControlAvailable,
                  long jvmUsedBytes, long jvmMaxBytes, OffsetDateTime workerHeartbeatAt) {}
    record Settings(boolean schedulerEnabled,boolean crawlerEnabled,OffsetDateTime seenAt) {}
    private final JdbcClient db;
    private final HostControl host;
    ServerApi(JdbcClient db,HostControl host) { this.db=db; this.host=host; }

    @GetMapping("/status")
    Status status() {
        Settings s=db.sql("""
                select scheduler_enabled,crawler_enabled,seen_at from collection_control
                left join worker_heartbeat on worker_heartbeat.id='tcg-worker'
                """).query(Settings.class).single();
        Runtime jvm=Runtime.getRuntime();
        return new Status("UP",s.schedulerEnabled(),s.crawlerEnabled(),host.available(),
                jvm.totalMemory()-jvm.freeMemory(),jvm.maxMemory(),s.seenAt());
    }

    @PostMapping("/sync") @ResponseStatus(HttpStatus.ACCEPTED) @Transactional
    void sync(Principal user) {
        db.sql("""
                update feed_source set requested_at=coalesce(requested_at,now()),next_fetch_at=now()
                where enabled and policy_note is null
                """).update();
        audit(user,"REQUEST_ALL_SOURCES");
    }

    @PostMapping("/{component:crawler|scheduler}/{operation:start|stop|pause|resume}")
    @ResponseStatus(HttpStatus.NO_CONTENT) @Transactional
    void collection(@PathVariable String component,@PathVariable String operation,Principal user) {
        String action=component+"/"+operation;
        switch (action) {
            case "crawler/start","crawler/stop" -> db.sql("update collection_control set crawler_enabled=?")
                    .param(action.endsWith("/start")).update();
            case "scheduler/pause","scheduler/resume" -> {
                db.sql("update collection_control set scheduler_enabled=?").param(action.endsWith("/resume")).update();
                if (action.endsWith("/pause")) db.sql("update feed_source set schedule_ready=false where schedule_ready").update();
            }
            default -> throw new org.springframework.web.server.ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        audit(user,action.replace('/','_').toUpperCase(java.util.Locale.ROOT));
    }

    @PostMapping("/restart") @ResponseStatus(HttpStatus.ACCEPTED)
    void restart(Principal user) { lifecycle(user, HostControl.Command.RESTART); }
    @PostMapping("/shutdown") @ResponseStatus(HttpStatus.ACCEPTED)
    void shutdown(Principal user) { lifecycle(user, HostControl.Command.SHUTDOWN); }

    private void lifecycle(Principal user,HostControl.Command command) {
        audit(user,"REQUEST_HOST_"+command.name());
        host.submit(command);
    }
    private void audit(Principal user,String action) {
        db.sql("insert into operator_action(user_id,action) select id,? from app_user where email=? and enabled and role='ROLE_ADMIN'")
                .param(action).param(user.getName()).update();
    }
}
