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

    @GetMapping({"/","/cards","/cards/{id:[0-9]+}","/releases","/releases/{id:[0-9]+}","/news","/play","/stores","/binder","/decks",
                 "/decks/new","/decks/{id:[0-9]+}","/shared/decks/{token}","/login","/admin","/admin/"})
    String app() { return "forward:/index.html"; }

    @GetMapping("/internal/ready")
    @ResponseBody Map<String,String> ready() {
        db.sql("select 1").query(Integer.class).single();
        return Map.of("status","UP");
    }

    @GetMapping("/media/{kind:sheets|banners|cards}/{name}")
    @ResponseBody ResponseEntity<FileSystemResource> media(@PathVariable String kind, @PathVariable String name) {
        if (!name.matches("[0-9a-f]{64}\\.webp")) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        Path path = media.resolve(kind).resolve(name);
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        String visibilitySql = switch (kind) {
            case "banners" -> "select exists(select 1 from pack where banner_key=?)";
            case "cards" -> """
                  select exists(select 1 from catalog_art_file f join catalog_art_card a on a.file_id=f.id
                      join card c on c.id=a.card_id where f.storage_key=? and c.status='PUBLISHED')
                  """;
            default -> """
                  select exists(
                      select 1 from image_sheet s join card_variant v on v.sheet_id=s.id
                        join card c on c.id=v.card_id
                      where s.storage_key=? and not s.retired group by s.id having bool_and(c.status='PUBLISHED'))
                  """;
        };
        if (!db.sql(visibilitySql).param(kind + "/" + name).query(Boolean.class).single()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return ResponseEntity.ok().contentType(MediaType.parseMediaType("image/webp"))
                .cacheControl(!kind.equals("banners") ? CacheControl.noCache()
                        : CacheControl.maxAge(java.time.Duration.ofDays(1)).cachePublic())
                .body(new FileSystemResource(path));
    }
}
