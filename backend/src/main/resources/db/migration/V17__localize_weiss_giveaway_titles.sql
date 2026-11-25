-- The old offline model reproduced these 49 faulty titles byte-for-byte. Match the
-- original, target language and stored title together so a review, later source edit,
-- or another installation's different translation remains intact.
WITH faulty(signature) AS (
    VALUES
        ('fb9bc496a372bb2e1759285384597f1c53a6080c963a31631aa8e8f6d9cd0de8'),
        ('f02ede1acef05d44522287fc342dacd06e4bb3f22d4ff4a522cd24966fc8c182'),
        ('58a3d3c8b1374476a1ccaf2303e59cb65e6cc9cf92396f2916f2aa0917c21e44'),
        ('ce0a9b073c46e342aedb050c8b5282480f71318fab106b36de9ba295696c8364'),
        ('ace533588dcf3b4dd6789cb7794b23f3c121e617155a4b625c7ae9723463728d'),
        ('a6eae5d913434cfc467c0995c7b2fa96df49abee7122a3930c5cb4cc0c2c8983'),
        ('2372df768a08447651863d208e4d8318a112d45514b325dc104bc6fb5d5aa81d'),
        ('8acd87f09f271c867022e7c12c78e9d422602906c385dfd2c888d24ed729fb29'),
        ('2aa15b4e2f23be1132e51166d006028c082b8aca981facb4f77e28b344c5e6cd'),
        ('6eed0f1ac1d987fe69fd0cb53060ce81e7ee96d12fd4771234200d3d016146fc'),
        ('bacb530e58f9f7c5b4ad2adb70776ff75ad142fd6b6d05c086402bdb26c1f0af'),
        ('98a8a12df5e03ded741b291a466c3cb2ed75d32c996e2603ce3dd1cf592f16ae'),
        ('470e9f253ceefcebeca69f3a859ae1266a2f35f1a16753c195381199e19c6549'),
        ('741ea3f23812202990dd339c3d8923a4bab9bc71fa5d0768027bb482db957423'),
        ('009ce4c5ba8c76ab26f81aeadd0fe4b41737840d02895e4620f16c93d73a5b62'),
        ('b56d15a98048d4fe157f1adf1f31ae90ccc51ac8de14bc64d6fb333de7523f59'),
        ('bcf9b826d5a2a8eb8ee6f377360b4c9337787d98e37d76664171fff677d0b4d7'),
        ('53c075fe60cb1ec2719fbbefb8f28fea4589d81fa8e4df2cdf74a448ab0658d5'),
        ('cacb62c37d71b0fe2567b81c20003a96772717638a8b9d57b9efa892fbf22c8c'),
        ('2388386ad6aad6d8c68d551c822eaee19e22dbca3084dcedc93550a7a3f1f350'),
        ('b7b5a422c7e0bbfb640264c9843913fc43b6c2b319cf9e9f2608ff39d791077e'),
        ('8e6493dac6fb70cc84cdd2ad36ad901c7a43846ca484cfdd561c7f750a6303e7'),
        ('366c7a4ba9de980887dd392bc8201f8d2bab89c99ca97d0c04a55b54034b40b3'),
        ('9a8eb2b2d4fb1d41d4b66bbb84e00c705c408d44740ae2fc9f128920725864f4'),
        ('6c9f165b71aa40a57d3dd63b133656335735d102ba908f9308c6d9635d31e3ec'),
        ('dbcc768112e1ae852bd8eb21604bedcbdb06aeb97e5ca12813cc3131c4a7a960'),
        ('c31644d6b95836b9691c52ae583795d4f46433f4748e0e25f6550ee4797fe18c'),
        ('14573a9b0515a43da42f3f68aabb033dbcbf917e481748bbb335dbdc4b401bee'),
        ('32bf1af5d81e86a4d41045a7d6fed58d785308e8a885c0e0585751c07254103d'),
        ('ce7742524fb9c0026d57659f0c3a6ae2a3eb35520cc8f1071ca4f0f61a8d925d'),
        ('9d6ed3d4a400679cdf81a7864016fda46f4d48619421bc57ae8d0da99ff948ac'),
        ('b0eef8463390f2173813a69c17eb738b44463e0279ba9d0a2227017debcd62da'),
        ('146649c6743647f680a49200e122240f7419cd49335f2fb5e8687fd6298eeb77'),
        ('ff80d4c8c6fad78921f8fc9d7ecbb722635f832460b1065ae421646cd1968cca'),
        ('f0993279fe64f88580f58a53da07fd200877c0c920977a24ebb0c1c62d91e231'),
        ('9b4f48d73a303ffdab52b56b8ac38ef3422c665e83437b72e3774b9e8998231a'),
        ('6ee9efa81a7d4c595a1d886c3b7727ef28ee236d8c31bfed427bb8d32e5b9615'),
        ('88cc31a5a9cdb48da96e051fc57e1ce00e2e58684dc14f04a4e7b0d6c25bfa74'),
        ('3f03e72650d9516689a90e5b5738b6b807be10a41a0d9cd3e0dca6a53098b02f'),
        ('8ef7cfc7572ef6afa35b4156d9df3ca67f9fbcb8afb74c66bbfc646426cdad97'),
        ('c6a16e7fc07f2468878c62c0f993aa75b67bcf5a793fffa8cb4a3b9e28add96c'),
        ('e99fe304dd4d21f38cd81ac8ba2a3f79b5e074700dea39e2daac7ac9a96a76e4'),
        ('71342732cebb6c8a9afaf0b8291fbd9a25d335a1620a22d8445078d746d216e5'),
        ('45b709b000354e724a60dc4e884a8d7e77cd332ebc855b3888ffa26ca28f72d9'),
        ('d292a5e88ffd109e2a81232d7b2f56c59545615b7803fd0be15816af1808fb6a'),
        ('5b8418a11e7cba70add0875f827a41e4172bbfcddf85232178fc428d58246e5d'),
        ('8a159565545e1245846bdff7979dda2d322774b683500af9a6b10015d1b15d85'),
        ('7ef0deeb706aca4bb6ef3947c041094392e90e540781d6443905fbf782eb8c56'),
        ('4a4195d09a7442631aace8e61f23ea6265449d91b85836eec5bca7179db3dd7a')
), matched AS (
    SELECT t.item_id,t.lang,t.title AS old_title,
           regexp_replace(i.payload->>'title','^(?:【Giveaway】|\[Giveaway\])[[:blank:]]*','') AS headline
    FROM feed_item_translation t JOIN feed_item i ON i.id=t.item_id
    JOIN feed_source s ON s.id=i.source_id
    JOIN faulty f ON f.signature=encode(sha256(convert_to(
        (i.payload->>'title') || chr(31) || t.lang || chr(31) || t.title,'UTF8')),'hex')
    WHERE s.provider='OFFICIAL_NEWS' AND s.source_key='weiss-en' AND s.policy_note IS NULL
      AND i.payload->>'kind'='NEWS' AND i.original_language='en' AND t.lang IN ('ko','ja')
      AND i.status IN ('PENDING','PUBLISHED')
), prizes AS (
    SELECT m.*,headline LIKE '% Winners' AS winners,
           regexp_replace(headline,' (Giveaway )?Winners$','') AS prize FROM matched m
), names AS (
    SELECT p.*,CASE WHEN k.kind IS NULL THEN p.prize ELSE ltrim(substr(p.prize,length(k.kind)+1)) END AS name,
           k.ko,k.ja FROM prizes p LEFT JOIN (VALUES
               ('Booster Pack','부스터 팩','ブースターパック'),
               ('Extra Booster','엑스트라 부스터','エクストラブースター'),
               ('Premium Booster','프리미엄 부스터','プレミアムブースター'),
               ('Trial Deck and Booster Pack','트라이얼 덱 및 부스터 팩','トライアルデッキ＆ブースターパック')
           ) k(kind,ko,ja) ON starts_with(p.prize,k.kind || ' ')
)
UPDATE feed_item_translation t SET title=
    CASE WHEN n.lang='ko' THEN n.name || coalesce(' ' || n.ko,'') || ' 증정 이벤트' ||
             CASE WHEN n.winners THEN ' 당첨자 발표' ELSE '' END
         ELSE coalesce(n.ja,'') || '「' || n.name || '」プレゼントキャンペーン' ||
             CASE WHEN n.winners THEN ' 当選者発表' ELSE '' END
    END
FROM names n WHERE t.item_id=n.item_id AND t.lang=n.lang AND t.title=n.old_title;
