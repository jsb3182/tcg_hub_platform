package kr.tcghub;

import java.time.OffsetDateTime;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/admin/community/reports")
class CommunityModerationApi {
    record Report(long id, long postId, Long commentId, String reason, String status, String title,
                  String excerpt, OffsetDateTime createdAt) {}
    record Decision(@NotNull @Pattern(regexp="RESOLVED|DISMISSED") String status) {}
    private final JdbcClient db;
    CommunityModerationApi(JdbcClient db) { this.db = db; }

    @GetMapping
    @Transactional(readOnly=true, isolation=Isolation.REPEATABLE_READ)
    CommunityApi.Page<Report> reports(@RequestParam(defaultValue="OPEN") @Pattern(regexp="OPEN|RESOLVED|DISMISSED") String status,
                                     @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                                     @RequestParam(defaultValue="20") @Min(1) @Max(100) int size) {
        var items = db.sql("""
                select r.id,p.id as post_id,r.comment_id,r.reason,r.status,p.title,
                       left(coalesce(c.body,p.body),240) as excerpt,r.created_at
                from abuse_report r left join post_comment c on c.id=r.comment_id
                join board_post p on p.id=coalesce(r.post_id,c.post_id)
                where r.status=? order by r.id desc limit ? offset ?
                """).param(status).param(size).param((long)page*size).query(Report.class).list();
        long total = db.sql("select count(*) from abuse_report where status=?").param(status).query(Long.class).single();
        return new CommunityApi.Page<>(items,page,size,total);
    }

    @PatchMapping("/{id}")
    @Transactional
    CommunityApi.Id decide(@PathVariable @Positive long id, @Valid @RequestBody Decision input) {
        record Target(long postId, Long commentId, String status) {}
        var target = db.sql("""
                select coalesce(r.post_id,c.post_id) as post_id,r.comment_id,r.status
                from abuse_report r left join post_comment c on c.id=r.comment_id where r.id=? for update of r
                """).param(id).query(Target.class).optional()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        if (target.status().equals(input.status())) return new CommunityApi.Id(id);
        if (!target.status().equals("OPEN")) throw new ResponseStatusException(HttpStatus.CONFLICT);
        if (input.status().equals("RESOLVED")) {
            if (target.commentId()==null) {
                db.sql("update board_post set hidden=true where id=?").param(target.postId()).update();
            } else {
                // Reply writers take a share lock on this post first. A reply cannot be added
                // after its parent is hidden or slip past the subtree snapshot during moderation.
                db.sql("select id from board_post where id=? for update").param(target.postId()).query(Long.class).single();
                db.sql("""
                        with recursive replies(id) as (
                            select id from post_comment where id=:comment and post_id=:post
                            union
                            select c.id from post_comment c join replies r on r.id=c.parent_id where c.post_id=:post
                        )
                        update post_comment set hidden=true where id in (select id from replies)
                        """).param("post",target.postId()).param("comment",target.commentId()).update();
            }
        }
        db.sql("update abuse_report set status=? where id=?").param(input.status()).param(id).update();
        return new CommunityApi.Id(id);
    }
}
