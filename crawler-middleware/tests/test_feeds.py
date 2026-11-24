import json
import os
import unittest
from unittest.mock import patch

from tcg_worker import feeds


def gallery(numbers):
    rows = "".join(f'<tr class="ub-content" data-no="{n}"><td class="gall_num">{n}</td>'
                   f'<td class="gall_tit"><a href="/post">Article {n}</a></td></tr>' for n in numbers)
    return (f'<table class="gall_list"><tbody>{rows}</tbody></table>'.encode(), {})


class FeedTests(unittest.TestCase):
    def test_permission_gate_makes_no_network_request(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(feeds, "download") as get:
            for provider, name in [("DCINSIDE", "tcggame"), ("X", "PlayRiftbound")]:
                with self.assertRaises(feeds.FetchError) as result:
                    feeds.fetch_feed(provider, name, {})
                self.assertTrue(result.exception.blocked)
            get.assert_not_called()

    def test_gallery_fills_incremental_pages_before_moving_high_water(self):
        with patch.dict(os.environ, {"DCINSIDE_WRITTEN_PERMISSION": "tcggame"}), \
             patch.object(feeds, "check_robots"), patch.object(feeds, "download") as get:
            get.side_effect = [gallery([104, 103]), gallery([103, 102]), gallery([101, 100])]
            page = feeds.dc_news("tcggame", {"latest": 100})
            self.assertEqual((page.cursor["latest"], page.cursor["high"], page.cursor["page"]), (100, 104, 2))
            page = feeds.dc_news("tcggame", page.cursor)
            self.assertEqual(page.cursor["page"], 3)
            page = feeds.dc_news("tcggame", page.cursor)
            self.assertEqual(page.cursor, {"latest": 104})
            self.assertEqual([p.external_id for p in page.items], ["101"])
            self.assertTrue(get.call_args.args[0].endswith("&page=3"))

    def test_x_pagination_retains_original_since_and_obeys_reset(self):
        payload = {"data": [{"id": "202", "text": "new card reveal"}],
                   "meta": {"next_token": "page2", "newest_id": "202"}}
        with patch.dict(os.environ, {"X_BEARER_TOKEN": "fixture"}), patch.object(feeds, "download") as get, \
             patch("time.time", return_value=900):
            get.return_value = (json.dumps(payload).encode(), {"x-rate-limit-remaining": "0", "x-rate-limit-reset": "1000"})
            page = feeds.x_news("PokemonTCG", {"uid": "99", "since": "200"})
            self.assertEqual(page.cursor, {"uid": "99", "since": "200", "high": "202", "page": "page2"})
            self.assertEqual(page.retry_after, 101)
            self.assertIn("카드 공개", page.items[0].title)
            get.return_value = (b'{"data":[],"meta":{"result_count":0}}', {})
            final = feeds.x_news("PokemonTCG", page.cursor)
            self.assertEqual(final.cursor, {"uid": "99", "since": "202"})
            self.assertIn("pagination_token=page2", get.call_args.args[0])

    def test_conditional_response_keeps_prior_validator(self):
        cursor = {"etag": '"snapshot"', "excerpts": 1}
        with patch.object(feeds, "check_robots"), patch.object(feeds, "download", return_value=(None, {})) as get:
            page = feeds.publisher_news("weiss-en", cursor)
            self.assertEqual(page.items, [])
            self.assertEqual(page.cursor, cursor)
            self.assertEqual(get.call_args.args[1], {"If-None-Match": '"snapshot"'})

    def test_existing_rss_cursor_fetches_publisher_excerpt_once(self):
        rss = b"""<rss><channel><item><link>https://en.ws-tcg.com/information/fixture</link>
                  <title>Booster set update</title><description><![CDATA[<p>Sample <b>release</b> news.</p>
                  <script>skip()</script>]]></description></item></channel></rss>"""
        with patch.object(feeds, "check_robots", return_value=0), patch.object(feeds, "download",
                return_value=(rss, {"ETag": '"new"'})) as get:
            page = feeds.publisher_news("weiss-en", {"etag": '"old"'})
        self.assertEqual(get.call_args.args[1], {})
        self.assertEqual(page.items[0].summary, "Sample release news.")
        self.assertEqual(page.cursor["excerpts"], 1)
