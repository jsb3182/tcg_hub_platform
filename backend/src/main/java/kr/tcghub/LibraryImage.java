package kr.tcghub;

import java.sql.ResultSet;
import java.sql.SQLException;

/** Fetch a single existing atlas tile without expanding a card into multiple print variants. */
final class LibraryImage {
    private LibraryImage() {}
    static final String COLUMNS=",tile.sheet_id,tile.col_idx,tile.row_idx,tile.storage_key,tile.cell_width,tile.cell_height ";
    static final String JOIN="""
         left join lateral (
            select v.sheet_id,v.col_idx,v.row_idx,s.storage_key,s.cell_width,s.cell_height
            from card_variant v join image_sheet s on s.id=v.sheet_id
            where v.card_id=c.id and c.status='PUBLISHED' and not s.retired order by v.position limit 1
         ) tile on true
        """;
    static CatalogApi.Image read(ResultSet row) throws SQLException {
        String key=row.getString("storage_key");
        return key==null?null:new CatalogApi.Image(row.getLong("sheet_id"),row.getInt("col_idx"),row.getInt("row_idx"),
                "/media/"+key,row.getInt("cell_width"),row.getInt("cell_height"));
    }
}
