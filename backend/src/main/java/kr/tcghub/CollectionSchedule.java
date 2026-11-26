package kr.tcghub;

import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@ConditionalOnWebApplication
class CollectionSchedule {
    private final JdbcClient db;
    CollectionSchedule(JdbcClient db) { this.db=db; }

    @Scheduled(fixedDelayString="${tcg.schedule-tick-ms:15000}")
    @Transactional
    public void enqueueDueSources() {
        db.sql("update collection_control set spring_managed=true where not spring_managed").update();
        db.sql("""
            update feed_source s set schedule_ready=true
             where not s.schedule_ready and s.enabled and s.policy_note is null and s.state <> 'RUNNING'
               and exists(select from collection_control where scheduler_enabled and crawler_enabled)
               and coalesce(s.next_fetch_at,'-infinity')<=now()
               and coalesce(s.retry_after_at,'-infinity')<=now()
               and not exists(select from feed_provider_cooldown p where p.provider=s.provider and p.retry_after_at>now())
            """).update();
    }
}
