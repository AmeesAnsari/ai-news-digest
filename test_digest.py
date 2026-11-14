import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import digest

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>New agent framework adds MCP support</title><link>https://ex.com/a?utm=1</link>
        <pubDate>Tue, 10 Nov 2026 09:00:00 GMT</pubDate><description>&lt;p&gt;Tool use for agents.&lt;/p&gt;</description></item>
  <item><title>Company picnic photos</title><link>https://ex.com/b</link>
        <pubDate>Tue, 10 Nov 2026 10:00:00 GMT</pubDate></item>
  <item><title>Old workflow automation post</title><link>https://ex.com/c</link>
        <pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Prompt injection in RAG pipelines</title>
         <link rel="alternate" href="https://blog.ex/rag"/><updated>2026-11-12T08:00:00Z</updated>
         <summary>Retrieval meets security.</summary></entry>
  <entry><title>Duplicate of the agent story</title><link href="https://ex.com/a"/>
         <published>2026-11-11T08:00:00Z</published></entry>
</feed>"""

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)


class ParseTests(unittest.TestCase):
    def test_rss_and_atom(self):
        rss = digest.parse_feed(RSS, "Ex")
        atom = digest.parse_feed(ATOM, "Blog")
        self.assertEqual(len(rss), 3)
        self.assertEqual(rss[0].summary, "Tool use for agents.")
        self.assertEqual(atom[0].link, "https://blog.ex/rag")
        self.assertEqual(atom[0].published, datetime(2026, 11, 12, 8, tzinfo=timezone.utc))

    def test_bad_date_is_none(self):
        self.assertIsNone(digest.parse_date("not a date"))


class SelectTests(unittest.TestCase):
    def setUp(self):
        items = digest.parse_feed(RSS, "Ex") + digest.parse_feed(ATOM, "Blog")
        self.picked = digest.select(items, NOW - timedelta(days=7), per_source=5)

    def test_filters_old_offtopic_and_duplicates(self):
        # Picnic is off-topic, the 2024 post is too old, and the two ex.com/a links
        # are the same story (query string ignored): only the newer copy is kept.
        titles = [i.title for i in self.picked]
        self.assertEqual(titles, ["Prompt injection in RAG pipelines", "Duplicate of the agent story"])

    def test_atom_prefers_alternate_link(self):
        feed = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Agents</title>
            <link rel="self" href="https://ex.com/self"/><link rel="alternate" href="https://ex.com/post"/>
            <updated>2026-11-12T08:00:00Z</updated></entry></feed>"""
        self.assertEqual(digest.parse_feed(feed, "X")[0].link, "https://ex.com/post")

    def test_topics(self):
        rag = self.picked[0]
        self.assertIn("Safety & security", rag.topics)
        self.assertIn("Retrieval & data", rag.topics)

    def test_per_source_cap(self):
        items = digest.parse_feed(RSS, "Ex") * 3
        for n, item in enumerate(items):
            item.link = f"https://ex.com/{n}"
            item.title = "Agents everywhere"
        self.assertEqual(len(digest.select(items, NOW - timedelta(days=7), per_source=2)), 2)


class OutputTests(unittest.TestCase):
    def test_render_and_readme(self):
        items = digest.select(digest.parse_feed(RSS, "Ex"), NOW - timedelta(days=7), 5)
        md = digest.render(items, NOW - timedelta(days=7), NOW, 1, 1)
        self.assertIn("## Agents", md)
        self.assertIn("[New agent framework adds MCP support](https://ex.com/a?utm=1)", md)

        with tempfile.TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(f"intro\n{digest.README_START}\nold\n{digest.README_END}\nfooter\n")
            digest.update_readme(readme, "2026-11-14.md", items, NOW)
            text = readme.read_text()
            self.assertIn("digests/2026-11-14.md", text)
            self.assertNotIn("old", text)
            self.assertTrue(text.startswith("intro") and text.rstrip().endswith("footer"))


if __name__ == "__main__":
    unittest.main()
