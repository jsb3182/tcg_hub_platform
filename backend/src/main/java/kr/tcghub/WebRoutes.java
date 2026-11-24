package kr.tcghub;

import java.nio.file.*;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@Controller
class WebRoutes {
    private final Path media;
    private final JdbcClient db;
    WebRoutes(@Value("${tcg.media-root}") String media, JdbcClient db) {
        this.media = Path.of(media).toAbsolutePath().normalize();
        this.db = db;
    }

    @GetMapping({"/","/cards","/cards/{id:[0-9]+}","/login","/admin","/admin/"})
    String app() { return "forward:/index.html"; }

    @GetMapping("/internal/ready")
    @ResponseBody Map<String,String> ready() {
        db.sql("select 1").query(Integer.class).single();
        return Map.of("status","UP");
    }

    @GetMapping("/media/{kind:sheets|banners}/{name}")
    @ResponseBody ResponseEntity<FileSystemResource> media(@PathVariable String kind, @PathVariable String name) {
        if (!name.matches("[0-9a-f]{64}\\.webp")) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        Path path = media.resolve(kind).resolve(name);
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        String visibilitySql = kind.equals("banners")
                ? "select exists(select 1 from pack where banner_key=?)"
                : """
                  select exists(
                      select 1 from image_sheet s join card_variant v on v.sheet_id=s.id
                        join card c on c.id=v.card_id
                      where s.storage_key=? group by s.id having bool_and(c.status='PUBLISHED'))
                  """;
        if (!db.sql(visibilitySql).param(kind + "/" + name).query(Boolean.class).single()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return ResponseEntity.ok().contentType(MediaType.parseMediaType("image/webp"))
                .cacheControl(CacheControl.maxAge(java.time.Duration.ofDays(1)).cachePublic())
                .body(new FileSystemResource(path));
    }
}
