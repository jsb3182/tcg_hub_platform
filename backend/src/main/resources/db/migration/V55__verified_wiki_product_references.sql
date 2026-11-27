-- Bind the reference to an edition when its catalog pack exists, including after a fresh import.
CREATE TABLE wiki_product_reference (
    game_code text NOT NULL REFERENCES game(code),
    pack_code text NOT NULL,
    product_name text NOT NULL,
    catalog_product_hash text NOT NULL CHECK (catalog_product_hash ~ '^[0-9a-f]{64}$'),
    region text NOT NULL,
    release_date date NOT NULL,
    verification_url text NOT NULL,
    title text NOT NULL,
    document_url text NOT NULL,
    section text NOT NULL,
    snapshot_date date NOT NULL,
    snapshot_url text NOT NULL,
    snapshot_row integer NOT NULL CHECK (snapshot_row >= 0),
    article_sha256 text NOT NULL CHECK (article_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (game_code, pack_code, product_name)
);

WITH documents(game_code,title,document_url,section,snapshot_row,article_sha256) AS (VALUES
    ('WEISS','바이스 슈발츠','https://namu.wiki/w/%EB%B0%94%EC%9D%B4%EC%8A%A4%20%EC%8A%88%EB%B0%9C%EC%B8%A0',
     '4.2.1. 부스터',1667755,'ff7990d83788f952eafabe0ea3af874c256e7f07f9a29575c62326e84850470e'),
    ('RIFTBOUND','리프트바운드','https://namu.wiki/w/%EB%A6%AC%ED%94%84%ED%8A%B8%EB%B0%94%EC%9A%B4%EB%93%9C',
     '7. 카드 발매 정보',266848,'680cc700fe57783cfa6932388210564bb2c45e986953249c1e897c06646bfe4a')
), editions(game_code,pack_code,product_name,catalog_product_hash,release_date,verification_url) AS (VALUES
    ('WEISS','SAO/S47','Sword Art Online Re: Edit','b4d16e16e7c3747a6de3282a7b2425d2345bacdc55968b8a7a58ce3af98fc7e6',
     DATE '2017-04-28','https://en.ws-tcg.com/products/bp-sao-re/'),
    ('WEISS','SAO/S80','Sword Art Online -Alicization- Vol.2','bab5af02e15b2d5e9aed25f1267604f467eab450d97e33a722cd976628a638a4',
     DATE '2021-11-05','https://en.ws-tcg.com/products/bp-sao-al2/'),
    ('RIFTBOUND','OGN','Origins','12bbc81f1b2423158bf4807b87c8f35e525ebb6b8ac1786e1cd5dff3fc9eb935',
     DATE '2025-10-31','https://playriftbound.com/en-us/news/announcements/how-to-buy-riftbound/'),
    ('RIFTBOUND','UNL','Unleashed','ead1cbce54dee9bce1aaa6ee072a21fc7a090b018074990427e72ce3d5f9934d',
     DATE '2026-05-08','https://playriftbound.com/en-us/news/announcements/the-unleashed-overview/')
)
INSERT INTO wiki_product_reference(game_code,pack_code,product_name,catalog_product_hash,region,release_date,
    verification_url,title,document_url,section,snapshot_date,snapshot_url,snapshot_row,article_sha256)
SELECT e.game_code,e.pack_code,e.product_name,e.catalog_product_hash,'EN',e.release_date,e.verification_url,
       d.title,d.document_url,d.section,DATE '2026-08-29','https://archive.org/details/namuwiki-data-dump-20260829',
       d.snapshot_row,d.article_sha256
FROM editions e JOIN documents d USING(game_code);
