-- Riot Tournament Rules, 2026-10-09 §§402/601. The chosen champion counts towards 40.
-- Pin this version for new decks; retain every saved deck's v2 section keys and history.
INSERT INTO deck_rule(game_code,format,version,max_copies_per_card,details) VALUES
 ('RIFTBOUND','CONSTRUCTED',3,3,'{
  "source":"https://playriftbound.com/en-us/rules-hub/",
  "format":"1v1 Standard Constructed",
  "rulesDate":"2026-10-09","legalityDate":"2026-11-23",
  "coreRules":"https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/5c7946f7c3b8c6e0faff85ab6dadc6d2e721ea94.pdf",
  "tournamentRules":"https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/861752822d217edf37d9febaeaf77a7d924c1bb6.pdf",
  "banned":["Called Shot","Ekko, Recurrent","Draven, Vanquisher","Fight or Flight","Scrapheap","Stealthy Pursuer","Stacked Deck","Riven, Broken Blade","Zhonya’s Hourglass","Stellacorn Herder","Nocturne, Horrifying","Rhasa the Sunderer","Brynhir Thundersong","Dazzling Aurora","Baited Hook","The Arena’s Greatest","Aspirant’s Climb","Dreaming Tree","Obelisk of Power","Reaver’s Row","Star Spring","Emperor’s Dais"]
 }');
INSERT INTO deck_section_rule(game_code,format,rule_version,section,min_cards,max_cards) VALUES
 ('RIFTBOUND','CONSTRUCTED',3,'CHAMPION',1,1),('RIFTBOUND','CONSTRUCTED',3,'MAIN',39,39),
 ('RIFTBOUND','CONSTRUCTED',3,'RUNE',12,12),('RIFTBOUND','CONSTRUCTED',3,'LEGEND',1,1),
 ('RIFTBOUND','CONSTRUCTED',3,'BATTLEFIELD',3,3),('RIFTBOUND','CONSTRUCTED',3,'SIDE',0,10);
