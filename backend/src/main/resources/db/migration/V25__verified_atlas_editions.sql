-- Observed language of the pixels in a 4 x 3 atlas. The digest identifies the
-- exact WebP bytes, so the manifest can precede import and survive variant edits.
CREATE TABLE verified_atlas_edition (
    storage_key text NOT NULL CHECK (storage_key ~ '^sheets/[0-9a-f]{64}[.]webp$'),
    col_idx integer NOT NULL CHECK (col_idx BETWEEN 0 AND 3),
    row_idx integer NOT NULL CHECK (row_idx BETWEEN 0 AND 2),
    language text NOT NULL CHECK (language IN ('ko', 'en', 'ja')),
    PRIMARY KEY (storage_key, col_idx, row_idx)
);

-- The 82 original sheets were reviewed tile by tile, in row-major order.
-- j = Japanese, e = English, - = unconfirmed or unreferenced. No artwork is stored here.
WITH reviewed(digest, cells) AS (VALUES
    ('7b2e170715955ef03978559f9f252a515bba821b2bc44c08c86954d7f3cf4685', 'jjjjjjjjjjjj'),
    ('ed914280dfbb6a950e5422868d62823d3de34f05368b369b6064f4be352e7b9d', 'jjjjjjjjjjjj'),
    ('882713f1427c10edd335dce50d640bb61f477c8e3b9a50cd963f2239988b64e6', 'jjjjjjjjjjjj'),
    ('d919b17975deb07f48ac2ffcc9955c8f14e752a04bd7e047be21200a180e39d5', 'jjjjjjjjjjjj'),
    ('df1a37407c62012d1925760384031a9b34b1e908cbac58ec066fbc7032560bee', 'jjjjjjjjjjjj'),
    ('db21d0e4019128bfa63bed56a8f7d8cdd98d613cc02a3428497cb04d8d2f2264', 'jjjjjjjjjjjj'),
    ('6085a87bca29f3b4b11516fd55176792d9f3658693118b0a7c96a54c89820e7e', 'jjjjjjjjjjjj'),
    ('c856ace6cabc47e12959b36f82666c6545dba3b94dabb088ae8c1e22e96e5f09', 'jjjjjjjjjjjj'),
    ('25020af121e206325cde06bb8bb0abbb7e9e03a6ef1f848845ee704b0a3dffb7', 'jjjjjjjjjjjj'),
    ('22a7668dc4b5fe025705c0b5bc3c647138e389cff29e5cf6623bdd523b5ec418', 'jjjjjjjjjjjj'),
    ('79fd276c4f804044b0da520591acb80e638347e4af692b8936f19222d880c65a', 'jjjjjjjjjjjj'),
    ('98c14e7891dd36af32e2f0ab7702913b6bb23c7f0a1727f219f7fa70d4cf803b', 'jjjjjjjjjjjj'),
    ('51e134f51419a96c3abf89271e9ecc537af09f9b32c2aea5b199eaf10137d05b', 'jjjjjjjjjjjj'),
    ('e47eee1b6aace25b4a379add23fe1f4927dcfe9ba7fc8d275084f1b0946e7ac2', 'jjjjjjjjjjjj'),
    ('499bc0ab3bdcd0a873a93bd2d1c64d70f658cf97e4ab85be9e1135ae570c25d8', 'jjjjjjjjjjjj'),
    ('b8b8693eb8e5c5159c7e062e8db5f27fa4919d3db035d56d8a9be90312a65b39', 'jjjjjjjjjjjj'),
    ('912dfad37ba877a3d1aa82a7af8e2f58b4920dac325ff9489293523b949b9c35', 'jjjjjjjjjjjj'),
    ('13efec852678bd108762141fde02b4405c4214747eb928f242cc0dacf727b22c', 'jjjjjjjjjjjj'),
    ('1a12982a01e2b34510e4bdae81bf481f1c397c866bd9c0d737b8d44f26913778', 'jjjjjjjjjjjj'),
    ('e1b03910f8ccea5831b3a7ee01907087b790ab3f90bb85c2ae587bd3ee90d90e', 'jjjjjjjjjjjj'),
    ('3e6da346090e7139d322d8a469ad4049732254f209456649392c9ec6b17596e5', 'jjjjjjjjjjjj'),
    ('f7cf5e017b304ae352f537526ca7bac998105488740ea4bae44f6a3df118e2df', 'jjjjjjjjjjjj'),
    ('d7659e43d3b09be320e47cf167a0b35edfe72549a0d2cf8e3745f0bec878bbd4', 'jjjjjjjjjjjj'),
    ('5cba1c695001a2aa7f51c81713d496bd923dd27abb59d45fd6a58a946cd0b735', 'jjjjjjjjjjjj'),
    ('a934ee536b65d01fc3fec153d918cf02ed9a9fce45397ba4d5ac1b2da70fbb04', 'jjjjjjjjjjjj'),
    ('3b5667988a963142ff1f38bc4f178c42988f6b35908bc606a1601647dd516f86', 'jjjjjjjjjjjj'),
    ('6b08b9f695fbc834dab48ed35271df134c606a658b27a67623a5ab5f9d457023', 'jjjjjjjjjjjj'),
    ('e7f26b7306fff37ce8e0186f243651bc24ea15345d83f56f2b5700c70f0b6d48', 'jjjjjjjjjjjj'),
    ('436a9193a7c7375c1b6427b48e36ac6e9e23e610323234be4c69e19bef03b9cc', 'jjjjjjjjjjjj'),
    ('9c5c462fc7caee0d690b601f7a420311444f58c4d1050fe61ee96b016404541e', 'jjjjjjjjjjjj'),
    ('d13d249cd834740e01e1cc243313400022bb74fe580a2a800b96cf079e970ef2', 'jjjjjjjjjjjj'),
    ('26d846b0df33be73692da6e5da0e92b1dcc03b865585e07d9c0fe445919a4243', 'jjjjjjjjjjjj'),
    ('466ba05415cba174187163baafa4230ad21deaea1d9682a1fbb385f351368a13', 'jjjjjjjjjjjj'),
    ('790d881850569963d47b5151244a273c8873c92e47080a965a2b99eea83a6865', 'jjjjjjjjjjjj'),
    ('0269bf3a2c1538fd4ca4aaf513d4fbacc1f8fe0773212d577ec1e7145e2b913e', 'jjjjjjjjjjjj'),
    ('1df415b51928582d2fa064b464f1c8db2e9fb6c87d87dea337d07e455789ed05', 'jjjjjjjjjjjj'),
    ('65c3307f0dfbcf5a6c2bc3d8237dcb0534ebc3a5b62ba4c88d4be7ba0be631b1', 'jjjjjjjjjjjj'),
    ('1f2b79b037e5cdf1b9c440b03b11b54b2ef649e14131f949feaf0793ca80f29d', 'jjjjjjjjjjjj'),
    ('1745f3e0486cfb36a8f4ce6fd2f435ea592602105c24406e5f298b3c44e2065e', 'jjjjjjjjjejj'),
    ('d7bfec4d8f621667f2a0ee133fd111ffe1b05d6e463ce8a54aa7728f6a760658', 'jjjjjeeeeeee'),
    ('901461f44978d2d110d19cfd1ad4ff59da6c6ae28b81dbeb8ddc66b328499b13', 'eeeeeeeeeeee'),
    ('819793cba868b66b6b679ba9854f407e33512b3542a8d2d3cf5a4f99bcb273fc', 'eeeeeeeeeeee'),
    ('06586174555fdd12ca20e67aec0573912742c1668d4cceb033f1e339b04b4147', 'eeee--------'),
    ('8ade58fa69ba313a479493850525b326f3b655b4b0bc81031167bcd4b7818581', 'jjjjjjjjjjjj'),
    ('f4b6ae607a7485ca71b1ebd58d0d6074cb5c710ae115596bd2ee1eed1faf8287', 'jjjjjjjjjjjj'),
    ('0c1711aefecd49405d76cdadfdb0de169ca45b405aa69a239d16eb4b2a7a24d6', 'jjjjjjjjjjjj'),
    ('2c26a561f6c072ee26cca61b50ea49e8cc3dbce1a027ed6af8c3557fa6a3abb8', 'jjjjjjjjjjjj'),
    ('6075ac9583e55e598cd7b1fe609ebdc3041e51a7e100c7fb9aec653d8f387eef', 'j-jjjjjjjjjj'),
    ('87bc879228fba3296fe378c3fd8da64f5b218d7a30f2c75139616a35f18226b4', 'ejjje-------'),
    ('05f7fc5dda9c15a4ca270bf5df0ffbcc2f26cd8651d38a191f93419382edbdaf', 'jjjjjjjjjjjj'),
    ('79e07a098c85b0d35177f8add9fddd630689832b86d667cc55d42d8a9724ca77', 'jeeeeeeeeeee'),
    ('5dd36cab373a5dc126110ac5ed2702d4dd4932160fa7dc5c0242783d7b4ca259', 'eeeeeeeejjjj'),
    ('1b7b73bdfd8a7207334f1646af0dcc7d8c2eed897864836f62ed66686b977886', 'jjjjjjjjjjjj'),
    ('e6f3b87c9ed86c883ce86a43a96a86e9799b3540e0f9d403e9f668fe30125358', 'jjjjjjjjjjjj'),
    ('5a5f67a5159e74d1a5c7504b043d123bbdd18d67d35fd68d79535b0f03ece673', 'jjjjjjjjjjjj'),
    ('0c55795bb8246bbadf194ab4b50b0703bf0cafd1c24ec5fed809c519fab7a27c', 'jjjjjjjjjjjj'),
    ('0d0d412217506af3ae952e8f0595c8c02be384d4ffbc3bd58c7b0a76e0724eb4', 'jjjjjjjjjjjj'),
    ('1f472c23152f0cc2b6b4686ab550fe16881139e0369df68a88cadedd640f839b', 'jjjjjjjjjjjj'),
    ('25258e9f5b4aa21bdf53ab3f246b5e6b1efedb2ed625b3db85369ba318014a08', 'jjjjjjjjjjjj'),
    ('84c14d2c378b90855fd55a1e211f5e15caeb3b1b89938037d604f215e6d0d040', 'jjjjjjjjjjjj'),
    ('f3a196f52e9320e600a718562c323f90217241687a2a6f7c6fdc70e042d9ac62', 'jjjjjjjjjjjj'),
    ('0d2813a12f9b3957aa6f0cd82394afd37689c80127907aec618c24fbd1f973dc', 'jjjjjjjjjjjj'),
    ('8e41fcfd2191fedebd960f0031f33396e87aa56a1635723048e382d6a985bacc', 'jjjjjjjjjjjj'),
    ('c9bbbc998d6cc333bfb2dcaa43512f3b55efca1cda3abdd8876db87bb95c8dd7', 'jjjjjjjjjjjj'),
    ('37220147fc5560e15aff979e93b79c62112d2cf6aec1c7a3b8187fab9192122d', 'jjjjjjjjjjjj'),
    ('d5ba1ae60df2fd8d85a2578f2fd151be43b53523822401c2bbfed752891eb15b', 'jjjjjjjjjjjj'),
    ('6c174939750e847126cbb3fa1c3439295bb85e6df68e44781c35ce553af15b41', 'jjjjjjjjjjjj'),
    ('09d251aaaabfb914d5925c0b8e41dd15dc0480a3e34551055441db324562e6f6', 'jjjjjjjjjjjj'),
    ('d39215cd9a6a460571b0bb7b86b07336c6b0082fd55596d0309d43bba08dbcb5', 'jjjjjjjjjjjj'),
    ('5da85e6d05d9685e61baf253c66be771af892c1957a046eeb963eaa00daee4c4', 'jjjjjjjjjjjj'),
    ('0e16958c256b33372b433f8f02ff52cd60f5615783b30d090066dd6212229f7d', 'jjjjjjjjjjjj'),
    ('64383d741f93d62af25934819acb22a0379fa9c4d6cdfcf416a7edcbf4255eb1', 'jjjjjjjjjjjj'),
    ('64ed66a09b66f0d8eff4cd97e9be2a24a586501059e9cea2a49bb56cdccf4970', 'jjjjjjjjjjjj'),
    ('a44e21db4865d9a6a266b33bf8c281925c06d9d9d150d2a6da0529418f2ac200', 'jjjjjjjjjjjj'),
    ('fdb948c0394564a8ce1789a3ba257f55b97c60f5c9942d984d8d48ad2fac9209', 'jjjjjjjjjjjj'),
    ('e3b0fc741dad82d3d277b3bdb8ac59eb0a75607b7847608e05e0c6da841894d8', 'jjjjjjjjjjjj'),
    ('e6ae4f6dc2dfbe2e624ff7744ac31c2ea8abb4baff0edae25934d35f0f19cd43', 'jjj---------'),
    ('72eabbe670f8a31b5fdc8716ef9e47fd5be93ab5d9723033c3785d56b0755f3f', 'jjjjjjjjjjjj'),
    ('395f175d01c18ad6bb81c71899fa2a7d55c24c87c5ee9fd3a6bb54fbc13f908f', 'jjjjjjjjjjjj'),
    ('d7aff14d9f3f3a3266bf0aac2c937299b6d514cfc0870418e9b7a9bd9259470d', 'jjjjjjjjjjjj'),
    ('261f27e5514cdbddb129449795ae9e14c6eb1e6c2e8fde093b08702d9a40ae91', 'jjjjjjjjjjjj'),
    ('9d8cd1914dbaa4746444d06e0535179cfca2695bd3fa7fd1ee5e4585cb225bd3', 'jj----------')
)
INSERT INTO verified_atlas_edition(storage_key, col_idx, row_idx, language)
SELECT 'sheets/' || digest || '.webp', n % 4, n / 4,
       CASE substr(cells, n + 1, 1) WHEN 'j' THEN 'ja' WHEN 'e' THEN 'en' END
FROM reviewed CROSS JOIN generate_series(0, 11) AS slots(n)
WHERE substr(cells, n + 1, 1) IN ('j', 'e');

-- V14/V15 kept public cells at their original coordinates but re-encoded four
-- partial sheets against a blank background. These exact hashes were reproduced
-- with the historical crop and WebP encoder. Other pre-migration outputs are unknown.
WITH rebuilt(original_digest, rebuilt_digest) AS (VALUES
    ('06586174555fdd12ca20e67aec0573912742c1668d4cceb033f1e339b04b4147',
     'ecea028b0438798995c57a974b5360c5f860c4c1a591c4c49a1cd4ec7968f0ad'),
    ('87bc879228fba3296fe378c3fd8da64f5b218d7a30f2c75139616a35f18226b4',
     'd1d73a6b3b75543079c219f01f234dfafaed18acac572825c91fdfe1d41a8856'),
    ('e6ae4f6dc2dfbe2e624ff7744ac31c2ea8abb4baff0edae25934d35f0f19cd43',
     '767cc6ef058650406491dfb272f6af8b48ed87f3fb010c6acf504e8575512433'),
    ('9d8cd1914dbaa4746444d06e0535179cfca2695bd3fa7fd1ee5e4585cb225bd3',
     '99b8c2af30d84fbcac13477259a0cffe47656383c96effae7eb989d692f757e8')
)
INSERT INTO verified_atlas_edition(storage_key, col_idx, row_idx, language)
SELECT 'sheets/' || r.rebuilt_digest || '.webp', e.col_idx, e.row_idx, e.language
FROM rebuilt r JOIN verified_atlas_edition e ON e.storage_key = 'sheets/' || r.original_digest || '.webp';
