package kr.tcghub;

import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/admin/providers")
class AdminProviderApi {
    record Provider(String code, boolean requiresKey, boolean configured) {}
    record Status(List<Provider> providers, Long cacheBytes) {}
    private final JdbcClient db;
    private final Path root;
    private long nextCheck;
    private Long cached;

    AdminProviderApi(JdbcClient db,@Value("${app.storage.card-images-dir}") String directory) {
        this.db=db;
        root=Path.of(directory);
    }

    @GetMapping
    Status status() {
        var providers=db.sql("select provider as code,requires_key,configured from provider_configuration order by provider")
                .query(Provider.class).list();
        return new Status(providers,storageBytes());
    }

    private synchronized Long storageBytes() {
        long now=System.nanoTime();
        if (nextCheck!=0 && now-nextCheck<0) return cached;
        nextCheck=now+java.time.Duration.ofMinutes(5).toNanos();
        if (!Files.isDirectory(root)) return cached=0L;
        long[] bytes={0};
        try {
            Files.walkFileTree(root,new SimpleFileVisitor<Path>() {
                @Override public FileVisitResult visitFile(Path path,BasicFileAttributes info) {
                    if (info.isRegularFile() && path.getFileName().toString().endsWith(".webp")) bytes[0]+=info.size();
                    return FileVisitResult.CONTINUE;
                }
            });
            return cached=bytes[0];
        } catch (IOException e) {
            return cached=null;
        }
    }
}
