import io
import json
import os
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from tcg_worker import feeds


def headers(**values):
    message = Message()
    for key, value in values.items():
        message[key] = value
    return message


class Response(io.BytesIO):
    status = 200

    def __init__(self, payload, **fields):
        super().__init__(json.dumps(payload).encode())
        self.headers = headers(**fields)


def timeline(ids, next_token=None, **fields):
    meta = {"result_count": len(ids)}
    if ids:
        meta.update(newest_id=str(max(ids)), oldest_id=str(min(ids)))
    if next_token:
        meta["next_token"] = next_token
    return Response({"data": [{"id": str(number)} for number in ids], "meta": meta}, **fields)


def failure(status, payload, **fields):
    return HTTPError("https://api.x.com/", status, "fixture", headers(**fields),
                     io.BytesIO(json.dumps(payload).encode()))


class XContinuityTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"X_BEARER_TOKEN": "test-only"}))
        self.enterContext(patch("time.time", return_value=1000))
        self.open = self.enterContext(patch.object(feeds, "build_opener")).return_value.open
        self.floors = []

    def fetch(self, cursor):
        return feeds.fetch_feed("X", "Test", cursor, on_x_limit=self.floors.append)

    def query(self):
        return parse_qs(urlsplit(self.open.call_args.args[0].full_url).query)

    def test_expired_opaque_token_restarts_from_committed_since_and_finishes_using_exclusive_id(self):
        invalid = {"errors": [{"parameters": {"pagination_token": ["previous"]},
                               "message": "The supplied pagination token is not valid."}]}
        self.open.side_effect = [failure(400, invalid), timeline([109, 108], "previous"),
                                 timeline([107, 106], "previous"), timeline([105, 104, 103, 102, 101])]
        cursor = {"uid": "99", "since": "100", "page": "previous", "high": "108"}
        recovery = self.fetch(cursor)
        self.assertTrue(recovery.more)
        self.assertEqual(recovery.cursor, {"uid": "99", "since": "100", "id_pages": True})
        self.assertEqual(self.open.call_count, 1)
        first = self.fetch(recovery.cursor)
        self.assertEqual(self.query()["since_id"], ["100"])
        self.assertNotIn("pagination_token", self.query())
        self.assertNotIn("until_id", self.query())
        second = self.fetch(first.cursor)
        self.assertEqual(self.query()["until_id"], ["108"])
        self.assertNotIn("pagination_token", self.query())
        last = self.fetch(second.cursor)
        self.assertEqual(self.query()["until_id"], ["106"])
        ids = {int(item.external_id) for page in (first, second, last) for item in page.items}
        self.assertEqual(ids, set(range(101, 110)))
        self.assertFalse(last.more)
        self.assertEqual(last.cursor, {"uid": "99", "since": "109"})

    def test_generic_400_preserves_checkpoint_and_does_not_retry_in_same_poll(self):
        self.open.side_effect = failure(400, {"title": "Invalid Request", "detail": "Invalid user ID."})
        cursor = {"uid": "99", "since": "100", "page": "previous"}
        with self.assertRaises(feeds.FetchError):
            self.fetch(cursor)
        self.assertEqual(cursor["page"], "previous")
        self.assertEqual(self.open.call_count, 1)

    def test_alternating_tokens_with_no_older_records_restart_by_id(self):
        self.open.side_effect = [timeline([109,108],"A"), timeline([107,106],"B"), timeline([107,106],"A")]
        cursor = {"uid": "99", "since": "100"}
        for _ in range(3):
            cursor = self.fetch(cursor).cursor
        self.assertEqual(cursor, {"uid": "99", "since": "100", "id_pages": True})

    def test_lookup_exhaustion_publishes_shared_floor_then_defers_timeline(self):
        self.open.side_effect = [Response({"data": {"id": "99"}}, **{"X-Rate-Limit-Remaining": "0",
                                   "X-Rate-Limit-Reset": "1090"}), timeline([119])]
        lookup = self.fetch({})
        self.assertTrue(lookup.more)
        self.assertEqual(lookup.cursor, {"uid": "99"})
        self.assertEqual(self.floors, [91])
        self.assertEqual(self.open.call_count, 1)
        self.assertIn("/by/username/", self.open.call_args.args[0].full_url)
        self.assertEqual(self.fetch(lookup.cursor).cursor["since"], "119")
        self.assertIn("/99/tweets?", self.open.call_args.args[0].full_url)

    def test_429_on_either_endpoint_shares_later_of_retry_and_reset(self):
        for cursor in ({}, {"uid": "99"}):
            for fields, expected in [({"Retry-After": "10", "X-Rate-Limit-Reset": "1040"}, 41),
                                     ({"Retry-After": "120", "X-Rate-Limit-Reset": "1040"}, 120),
                                     ({}, 60)]:
                self.open.side_effect = failure(429, {}, **fields)
                with self.assertRaises(feeds.FetchError) as caught:
                    self.fetch(cursor)
                self.assertEqual(caught.exception.retry_after, expected)
                self.assertEqual(self.floors[-1], expected)

    def test_success_floor_is_observed_before_invalid_body_can_discard_it(self):
        self.open.return_value = Response({"data": [{}], "meta": {"result_count": 1}},
                                          **{"x-rate-limit-remaining": "0", "x-rate-limit-reset": "1010"})
        with self.assertRaises(feeds.FetchError):
            self.fetch({"uid": "99", "since": "100"})
        self.assertEqual(self.floors, [11])

    def test_malformed_responses_never_advance_checkpoint(self):
        invalid = [{"meta": {}}, {"meta": {"result_count": False}},
                   {"meta": {"result_count": 0, "next_token": "bad"}},
                   {"meta": {"result_count": 1}, "data": []},
                   {"data": [{"id": "110"}], "meta": {"newest_id": "120"}},
                   {"data": [{"id": "110"}], "meta": {"result_count": 1, "oldest_id": "109"}},
                   {"data": [{"id": "not-an-id"}], "meta": {"result_count": 1}},
                   {"data": [{"id": "0001"}], "meta": {"result_count": 1}}]
        for reply in invalid:
            with self.subTest(reply=reply):
                self.open.return_value = Response(reply)
                with self.assertRaises(feeds.FetchError):
                    self.fetch({"uid": "99", "since": "100"})
        self.open.return_value = timeline([])
        self.assertEqual(self.fetch({"uid": "99", "since": "100"}).cursor, {"uid": "99", "since": "100"})
        bad_json = Response(None)
        bad_json.seek(0)
        bad_json.write(b"{broken")
        bad_json.seek(0)
        self.open.return_value = bad_json
        with self.assertRaises(feeds.FetchError):
            self.fetch({"uid": "99", "since": "100"})
