package kr.tcghub;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.util.HexFormat;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/admin")
class AdminMediaApi {
    private static final Logger LOG = LoggerFactory.getLogger(AdminMediaApi.class);
    record Job(long id, long variantId, String status, String error) {}
    private record Variant(String status, Long sheetId) {}
    private record Previous(long id, String inputHash, String status) {}
    private final JdbcClient db;
    private final Path spool;

    AdminMediaApi(JdbcClient db, @Value("${tcg.spool-root:${SPOOL_ROOT:/var/lib/tcg-hub/spool}}") String privateRoot,
                  @Value("${tcg.media-root}") String publicRoot) {
        this.db = db;
        spool = Path.of(privateRoot).toAbsolutePath().normalize();
        Path media = Path.of(publicRoot).toAbsolutePath().normalize();
        if (spool.startsWith(media) || media.startsWith(spool)) {
            throw new IllegalArgumentException("SPOOL_ROOT and MEDIA_ROOT must be separate directories");
        }
    }

    @PostMapping(path="/variants/{variantId}/image", consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.ACCEPTED)
    @Transactional(rollbackFor=IOException.class)
    Job upload(@PathVariable long variantId, @RequestPart("file") MultipartFile file,
               Principal principal) throws IOException {
        long user = db.sql("select id from app_user where email=? and role='ROLE_ADMIN' and enabled")
                .param(principal.getName()).query(Long.class).optional()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.FORBIDDEN));
        byte[] cell = UploadCell.normalize(file);
        String digest;
        try { digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(cell)); }
        catch (NoSuchAlgorithmException ex) { throw new IllegalStateException(ex); }
        var variant = db.sql("""
                select c.status,v.sheet_id from card_variant v join card c on c.id=v.card_id
                where v.id=? for update of v for share of c
                """).param(variantId).query(Variant.class).optional().orElseThrow(AdminMediaApi::missing);
        if (!"PUBLISHED".equals(variant.status())) throw new ResponseStatusException(HttpStatus.CONFLICT);
        var last = db.sql("select id,input_hash,status from media_job where variant_id=? order by id desc limit 1")
                .param(variantId).query(Previous.class).optional();
        if (last.isPresent() && digest.equals(last.get().inputHash()) &&
                ("PENDING".equals(last.get().status()) || ("DONE".equals(last.get().status()) && variant.sheetId()!=null))) {
            return new Job(last.get().id(),variantId,last.get().status(),null);
        }
        // An interrupted upload can be reclaimed only after its transaction releases this lock.
        db.sql("select pg_advisory_xact_lock_shared(83269432)").query((row,n) -> 0).single();
        String key = UUID.randomUUID().toString().replace("-","") + ".png";
        long id = db.sql("insert into media_job(variant_id,input_hash,spool_key) values(?,?,?) returning id")
                .params(variantId,digest,key).query(Long.class).single();
        db.sql("insert into operator_action(user_id,action,target_id) values(?,'UPLOAD_VARIANT_IMAGE',?)")
                .params(user,variantId).update();
        Files.createDirectories(spool);
        Path path = spool.resolve(key);
        try (var channel = FileChannel.open(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override public void afterCompletion(int status) {
                    // An indeterminate DB commit is reconciled by the worker against committed rows.
                    if (status == STATUS_ROLLED_BACK) {
                        try { Files.deleteIfExists(path); }
                        catch (IOException ex) { LOG.warn("Private media spool cleanup deferred", ex); }
                    }
                }
            });
            ByteBuffer data = ByteBuffer.wrap(cell);
            while (data.hasRemaining()) channel.write(data);
            channel.force(true);
        }
        if (spool.getFileSystem().supportedFileAttributeViews().contains("posix")) {
            try (var directory = FileChannel.open(spool, StandardOpenOption.READ)) {
                directory.force(true);
            }
        }
        return new Job(id,variantId,"PENDING",null);
    }

    @GetMapping("/media-jobs/{id}")
    Job job(@PathVariable long id) {
        return db.sql("""
                select id,variant_id,status,
                       case when status='FAILED' then '이미지 처리에 실패했습니다. 파일을 확인하고 다시 등록하세요.' end as error
                from media_job where id=?
                """).param(id).query(Job.class).optional().orElseThrow(AdminMediaApi::missing);
    }

    private static ResponseStatusException missing() {
        return new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
}
