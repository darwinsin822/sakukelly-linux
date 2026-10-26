import unittest, tempfile
from pathlib import Path
from sakukelly.database.database import DB

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_library.db"
        self.db = DB(str(self.db_path))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_database_initialization(self):
        songs = self.db.songs()
        self.assertEqual(len(songs), 0)

    def test_upsert_stream(self):
        stream_row = {
            "id": "abc12345678",
            "title": "Test Track",
            "artist": "Test Artist",
            "duration": 210,
            "url": "https://www.youtube.com/watch?v=abc12345678",
            "thumbnail": "https://img.youtube.com/vi/abc12345678/hqdefault.jpg",
            "channel": "Test Channel"
        }
        self.db.upsert_stream(stream_row)
        retrieved = self.db.stream("abc12345678")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["title"], "Test Track")
        self.assertEqual(retrieved["artist"], "Test Artist")

    def test_playlists(self):
        self.db.newpl("Mi Lista")
        pls = self.db.pls()
        self.assertIn("Mi Lista", pls)

    def test_stream_history(self):
        stream_row = {
            "id": "hist1234567",
            "title": "History Track",
            "artist": "History Artist",
            "duration": 180
        }
        self.db.upsert_stream(stream_row)
        self.db.add_stream_history("hist1234567")
        hist = self.db.recent_streams(limit=5)
        self.assertTrue(len(hist) > 0)
        self.assertEqual(hist[0][0], "hist1234567")

if __name__ == "__main__":
    unittest.main()
