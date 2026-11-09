import unittest
from scripts.index_hn import video_id, category, build

class IndexTests(unittest.TestCase):
    def test_normalize(self):
        urls = ['https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=12', 'https://youtu.be/dQw4w9WgXcQ', 'https://m.youtube.com/shorts/dQw4w9WgXcQ', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ']
        for url in urls:
            self.assertEqual(video_id(url), 'dQw4w9WgXcQ')
    def test_reject(self):
        self.assertIsNone(video_id('https://notyoutube.com/watch?v=dQw4w9WgXcQ'))
        self.assertIsNone(video_id('https://youtube.com/watch?v=bad'))
    def test_category(self):
        self.assertEqual(category('How transformers power LLM'), 'AI')

if __name__ == '__main__':
    unittest.main()
