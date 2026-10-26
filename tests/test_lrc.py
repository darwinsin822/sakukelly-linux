import unittest
from sakukelly.lyrics.lyrics import parse_lrc, clean_lyrics_query, lyrics_cache_key

class TestLRCParser(unittest.TestCase):
    def test_parse_lrc_basic(self):
        text = "[01:23.45]Hello world\n[01:25.50]Second line"
        lines = parse_lrc(text)
        self.assertEqual(len(lines), 2)
        self.assertAlmostEqual(lines[0][0], 83.45, places=2)
        self.assertEqual(lines[0][1], "Hello world")
        self.assertAlmostEqual(lines[1][0], 85.50, places=2)
        self.assertEqual(lines[1][1], "Second line")

    def test_parse_lrc_with_offset(self):
        text = "[offset:+1000]\n[01:00.00]First line"
        lines = parse_lrc(text)
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(lines[0][0], 61.00, places=2)

    def test_clean_lyrics_query_vevo(self):
        queries = clean_lyrics_query("Taylor Swift - Cruel Summer (Official Video)", "TaylorSwiftVEVO")
        self.assertTrue(len(queries) > 0)
        artists = [q[0] for q in queries]
        self.assertIn("Taylor Swift", artists)

    def test_clean_lyrics_query_topic(self):
        queries = clean_lyrics_query("Yellow", "Coldplay - Topic")
        self.assertTrue(len(queries) > 0)
        artists = [q[0] for q in queries]
        self.assertIn("Coldplay", artists)

    def test_lyrics_cache_key(self):
        key1 = lyrics_cache_key("Coldplay", "Yellow")
        key2 = lyrics_cache_key("coldplay ", " YELLOW ")
        self.assertEqual(key1, key2)

if __name__ == "__main__":
    unittest.main()
