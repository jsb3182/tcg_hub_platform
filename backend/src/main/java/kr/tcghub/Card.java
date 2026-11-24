package kr.tcghub;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.Immutable;

/** Read model. Flyway owns the schema and the importer owns catalog writes. */
@Entity
@Immutable
class Card {
    @Id private Long id;
    private String name;
    protected Card() {}
}
