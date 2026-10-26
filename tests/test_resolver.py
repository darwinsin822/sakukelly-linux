import unittest, time
from sakukelly.streaming.resolver import _STREAM_URL_CACHE, _SEARCH_CACHE, CACHE_TTL, SEARCH_CACHE_TTL

class TestResolverCache(unittest.TestCase):
    def setUp(self):
        _STREAM_URL_CACHE.clear()
        _SEARCH_CACHE.clear()

    def test_stream_url_cache_ttl(self):
        video_id = "test_vid_001"
        test_url = "https://googlevideo.com/videoplayback?id=test_vid_001"
        _STREAM_URL_CACHE[video_id] = (test_url, time.time())

        self.assertIn(video_id, _STREAM_URL_CACHE)
        url, ts = _STREAM_URL_CACHE[video_id]
        self.assertEqual(url, test_url)
        self.assertTrue(time.time() - ts < CACHE_TTL)

    def test_search_cache_ttl(self):
        query_key = "coldplay yellow"
        mock_results = [{"id": "y123", "title": "Yellow", "artist": "Coldplay"}]
        _SEARCH_CACHE[query_key] = (mock_results, time.time())

        self.assertIn(query_key, _SEARCH_CACHE)
        res, ts = _SEARCH_CACHE[query_key]
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "y123")

if __name__ == "__main__":
    unittest.main()
