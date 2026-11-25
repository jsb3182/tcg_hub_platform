package kr.tcghub;

import java.io.File;
import java.security.Principal;
import java.time.OffsetDateTime;
import java.util.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/admin")
@Transactional
class OperationsApi {
    record Enabled(@NotNull Boolean enabled) {}
    enum Verdict { PUBLISHED, REJECTED }
    record Decision(@NotNull Verdict status, @Pattern(regexp="YUGIOH|POKEMON|WEISS|NIVEL|RIFTBOUND") String gameCode) {}
    record Source(long id, String provider, String name, String gameCode, boolean enabled, String state,
                  OffsetDateTime lastStartedAt, OffsetDateTime lastSuccessAt, OffsetDateTime lastErrorAt,
                  String lastError, OffsetDateTime nextFetchAt, OffsetDateTime runRequestedAt, int lastCount, int addedCount,
                  String policyNote) {}
    record SourceSettings(boolean enabled, String policyNote) {}
    record Heartbeat(OffsetDateTime seenAt, OffsetDateTime startedAt, OffsetDateTime restartRequestedAt, int restartCount) {}
    record Snapshot(long jvmUsedBytes, long jvmMaxBytes, long diskUsableBytes, long diskTotalBytes,
                    OffsetDateTime workerHeartbeatAt, OffsetDateTime workerStartedAt,
                    OffsetDateTime workerRestartRequestedAt, int workerRestartCount,
                    Map<String,Long> cardCounts, List<Source> sources) {}
    private final JdbcClient db;
    private final File media;
    OperationsApi(JdbcClient db, @Value("${tcg.media-root}") String media) {
        this.db = db;
        this.media = new File(media).getAbsoluteFile();
    }

    @GetMapping("/operations")
    @Transactional(readOnly=true)
    Snapshot operations() {
        var beat = db.sql("""
            select seen_at,started_at,restart_requested_at,restart_count from worker_heartbeat where id='tcg-worker'
            """).query(Heartbeat.class).single();
        var counts = new TreeMap<String,Long>();
        db.sql("""
            select g.code,count(c.id) from game g left join card c on c.game_code=g.code and c.status='PUBLISHED'
            group by g.code
            """).query((rs,n) -> Map.entry(rs.getString(1),rs.getLong(2))).list()
                .forEach(e -> counts.put(e.getKey(),e.getValue()));
        var sources = db.sql("""
            select id,provider,coalesce(label,source_key) as name,game_code,enabled,
                   case when not enabled then 'PAUSED' when state='RUNNING' then state
                        when requested_at is not null then 'QUEUED' else state end as state,
                   last_started_at,last_success_at,last_error_at,last_error,
                   greatest(s.next_fetch_at,s.retry_after_at,p.retry_after_at) as next_fetch_at,requested_at as run_requested_at,
                   last_seen as last_count,last_added as added_count,s.policy_note
            from feed_source s left join feed_provider_cooldown p using (provider)
            order by provider,game_code nulls last,id
            """).query(Source.class).list();
        File mount = media;
        while (!mount.exists() && mount.getParentFile() != null) mount = mount.getParentFile();
        var jvm = Runtime.getRuntime();
        return new Snapshot(jvm.totalMemory()-jvm.freeMemory(),jvm.maxMemory(),mount.getUsableSpace(),mount.getTotalSpace(),
                beat.seenAt(),beat.startedAt(),beat.restartRequestedAt(),beat.restartCount(),counts,sources);
    }

    @PostMapping("/sources/{id}/enabled")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void enable(@PathVariable @Positive long id, @Valid @RequestBody Enabled body, Principal principal) {
        var source = lockSource(id);
        if (body.enabled() && source.policyNote()!=null) throw new ResponseStatusException(HttpStatus.CONFLICT);
        db.sql("""
            update feed_source set enabled=:enabled,requested_at=null,
                next_fetch_at=case when :enabled and not enabled then now() else next_fetch_at end where id=:id
            """).param("id",id).param("enabled",body.enabled()).update();
        audit(principal,body.enabled() ? "ENABLE_SOURCE" : "PAUSE_SOURCE",id);
    }

    @PostMapping("/sources/{id}/run")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void run(@PathVariable @Positive long id, Principal principal) {
        var source = lockSource(id);
        if (!source.enabled() || source.policyNote()!=null) throw new ResponseStatusException(HttpStatus.CONFLICT);
        db.sql("update feed_source set requested_at=coalesce(requested_at,now()),next_fetch_at=now() where id=?")
                .param(id).update();
        audit(principal,"REQUEST_SYNC",id);
    }

    @PostMapping("/worker/restart")
    @ResponseStatus(HttpStatus.ACCEPTED)
    void restart(Principal principal) {
        db.sql("""
            update worker_heartbeat set restart_requested_at=coalesce(restart_requested_at,now()) where id='tcg-worker'
            """).update();
        audit(principal,"RESTART_WORKER",null);
    }

    @PostMapping("/review/{id}/decision")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void review(@PathVariable @Positive long id, @Valid @RequestBody Decision body, Principal principal) {
        var prior = db.sql("""
            select i.status from feed_item i join feed_source s on s.id=i.source_id
            where i.id=? and i.payload->>'kind'='NEWS' and s.policy_note is null for update of i,s
            """).param(id)
                .query(String.class).optional().orElseThrow(OperationsApi::missing);
        if (prior.equals(body.status().name())) return;
        if (!prior.equals("PENDING")) throw new ResponseStatusException(HttpStatus.CONFLICT);
        long user = adminId(principal);
        db.sql("""
            update feed_item i set status=:status,reviewer_id=:user,
              payload=case when :status='PUBLISHED' and cast(:game as text) is not null and s.game_code is null
                           then i.payload || jsonb_build_object('gameCode',cast(:game as text)) else i.payload end
            from feed_source s where i.id=:id and s.id=i.source_id
            """).param("status",body.status().name()).param("user",user).param("id",id)
                .param("game",body.gameCode(),java.sql.Types.VARCHAR).update();
        audit(principal,"REVIEW_" + body.status(),id);
    }

    private SourceSettings lockSource(long id) {
        return db.sql("select enabled,policy_note from feed_source where id=? for update").param(id)
                .query(SourceSettings.class).optional().orElseThrow(OperationsApi::missing);
    }

    private long adminId(Principal principal) {
        return db.sql("select id from app_user where email=? and enabled and role='ROLE_ADMIN'")
                .param(principal.getName()).query(Long.class).optional()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.FORBIDDEN));
    }

    private void audit(Principal principal, String action, Long target) {
        db.sql("insert into operator_action(user_id,action,target_id) values(:user,:action,:target)")
                .param("user",adminId(principal)).param("action",action).param("target",target,java.sql.Types.BIGINT).update();
    }

    private static ResponseStatusException missing() { return new ResponseStatusException(HttpStatus.NOT_FOUND); }
}
