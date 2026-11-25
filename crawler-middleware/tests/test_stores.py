import csv
import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from tcg_worker import stores


class StoreDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.row = {"상가업소번호":"MA0101202608A0104832","상호명":"카드웨이브강릉","지점명":"",
                    "도로명주소":"강원특별자치도 강릉시 솔올로 40","경도":"128.9","위도":"37.7",
                    "시도명":"강원특별자치도","상권업종소분류명":"장난감 소매업"}

    def test_reviewed_profile_requires_the_same_business_name_and_building(self):
        record=stores.select_store(self.row)
        self.assertEqual(record["games"],{"POKEMON":stores.POKEMON+"809"})
        self.assertIn("월 휴무",record["hours"]["text"])
        self.assertIsNone(stores.select_store({**self.row,"도로명주소":"강원특별자치도 강릉시 솔올로 41"}))
        self.assertIsNone(stores.select_store({**self.row,"상호명":"다른 매장"}))

    def test_unrelated_businesses_and_unverified_games_stay_out(self):
        toy={**self.row,"상가업소번호":"MA0101202608A0105000","상호명":"TCG 가게"}
        self.assertEqual(stores.select_store(toy)["games"],{})
        self.assertIsNone(stores.select_store({**toy,"상권업종소분류명":"경영 컨설팅업"}))
        self.assertIsNone(stores.select_store({**toy,"상호명":"스포츠 카드샵"}))
        self.assertIsNone(stores.select_store({**toy,"상가업소번호":"MA010120220800050140"}))
        with self.assertRaises(ValueError):
            stores.select_store({**toy,"위도":"NaN"})

    def test_extract_requires_all_regions_from_a_single_quarter(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path=Path(tmp.name)/"stores.zip"
        regions=sorted(stores.REGIONS | {"전남광주"})
        def write(included):
            with ZipFile(path,"w") as archive:
                for region in included:
                    stream=io.StringIO()
                    writer=csv.DictWriter(stream,fieldnames=self.row)
                    writer.writeheader()
                    if region=="강원":
                        writer.writerow(self.row)
                    archive.writestr(f"소상공인시장진흥공단_상가(상권)정보_{region}_202609.csv",stream.getvalue())
        write(regions)
        edition,shops=stores.extract(path)
        self.assertEqual((str(edition),len(shops)),("2026-09-30",1))
        write(regions[:-1])
        with self.assertRaisesRegex(ValueError,"complete nationwide"):
            stores.extract(path)
