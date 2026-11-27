-- Keep live dates while linking regional product codes to the exact Korean catalog product.
UPDATE product_release SET catalog_code=replace(code,'K-','-'),catalog_name='['||code||'] '||name
WHERE game_code='ONEPIECE' AND region='KR' AND code ~ '^(OP|ST|EB|PRB)K-[0-9]{2}$'
  AND catalog_code IS NULL AND catalog_name IS NULL;
