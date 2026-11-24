import json
import os
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from tcg_worker import feeds


class Gallery:
    def __init__(self, numbers):
        self.numbers = list(numbers)
        self.unreadable = set()
        self.requests = []

    def download(self, url):
        page = int(parse_qs(urlsplit(url).query).get("page", ["1"])[0])
        self.requests.append(page)
        rows = []
        for post in self.numbers[(page - 1) * 2:page * 2]:
            title = "" if post in self.unreadable else f'<a href="/post/{post}">소식 {post}</a>'
            rows.append(f'<tr class="ub-content" data-no="{post}"><td class="gall_num">{post}</td>'
                        f'<td class="gall_tit">{title}</td></tr>')
        return ('<table class="gall_list"><tbody>' + "".join(rows) + "</tbody></table>").encode(), {}


class GalleryContinuityTests(unittest.TestCase):
    def setUp(self):
        self.gallery = Gallery(range(106, 98, -1))
        self.archive = set()
        for context in (patch.dict(os.environ, {"DCINSIDE_WRITTEN_PERMISSION": "tcggame"}),
                        patch.object(feeds, "download", side_effect=self.gallery.download),
                        patch.object(feeds, "check_robots", return_value=5)):
            context.start()
            self.addCleanup(context.stop)

    def fetch(self, cursor):
        page = feeds.dc_news("tcggame", json.loads(json.dumps(cursor)))
        self.archive.update(int(item.external_id) for item in page.items)
        return page

    def test_deletion_moves_unseen_post_to_a_previously_read_page(self):
        page = self.fetch({"latest": 100})
        self.gallery.numbers.remove(106)  # 104 moves from page 2 to the bottom of page 1.
        for _ in range(12):
            if not page.more:
                break
            self.assertEqual(page.cursor["latest"], 100)
            page = self.fetch(page.cursor)
        self.assertEqual(page.cursor, {"latest": 106})
        self.assertEqual(self.archive, set(range(101, 107)))
        self.assertLessEqual(len(self.gallery.requests), 9)

    def test_older_inflight_checkpoint_replays_and_newer_posts_wait(self):
        first = self.fetch({"latest": 100, "high": 105, "page": 3})
        self.assertEqual(self.gallery.requests, [1])
        self.assertEqual(self.archive, {105})
        page = first
        while page.more and len(self.gallery.requests) < 12:
            page = self.fetch(page.cursor)
        self.assertEqual(page.cursor, {"latest": 105})
        self.assertEqual(self.archive, set(range(101, 106)))
        self.assertEqual(self.fetch(page.cursor).cursor, {"latest": 106})

    def test_unreadable_numeric_rows_cannot_advance_any_checkpoint(self):
        for cursor in ({}, {"latest": 100}):
            self.gallery.unreadable = {106}
            with self.assertRaises(feeds.FetchError):
                self.fetch(cursor)
        self.gallery.unreadable.clear()
        first = self.fetch({"latest": 100})
        self.gallery.unreadable = {104}
        with self.assertRaises(feeds.FetchError):
            self.fetch(first.cursor)
        self.gallery.unreadable.clear()
        second = self.fetch(first.cursor)
        self.assertEqual([int(item.external_id) for item in second.items], [104, 103])

    def test_repeated_churn_backs_off_without_advancing(self):
        cursor = {"latest": 100}
        for rank in (112, 111, 110):
            self.gallery.numbers = [rank, 109, 103, 100]
            page = self.fetch(cursor)
            self.assertTrue(page.more)
            page = self.fetch(page.cursor)
            cursor = page.cursor
        self.assertFalse(page.more)
        self.assertGreaterEqual(page.retry_after, 3600)
        self.assertEqual((cursor["latest"], cursor["high"]), (100, 112))

    def test_page_limit_and_robots_gate(self):
        self.gallery.numbers = list(range(800, 300, -1))
        with self.assertRaises(feeds.FetchError) as cap:
            self.fetch({"latest": 100, "high": 800, "scan_version": 1, "page": 200})
        self.assertTrue(cap.exception.blocked)
        with patch.object(feeds, "check_robots", side_effect=feeds.FetchError("robots", retry_after=60)):
            with self.assertRaises(feeds.FetchError):
                self.fetch({"latest": 100})
        self.assertEqual(self.gallery.requests, [200])
