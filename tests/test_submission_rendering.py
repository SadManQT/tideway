"""Wrapped source text must survive rendering without lost or fragmented content."""
import unittest
from scripts.build_submission_pdfs import markdown_to_html


class SubmissionRendering(unittest.TestCase):
    def test_wrapped_paragraphs_and_list_items_stay_together(self):
        source = '# Review\n\nA sentence wraps\nonto its next line.\n\n- A rule applies\n  to every member.\n- Another rule.\n\n## Next\n\nFinal paragraph.'
        output = markdown_to_html(source)
        self.assertIn('<p>A sentence wraps onto its next line.</p>', output)
        self.assertIn('<li>A rule applies to every member.</li>', output)
        self.assertIn('<li>Another rule.</li>', output)
        self.assertIn('<h2>Next</h2>', output)
        self.assertIn('<p>Final paragraph.</p>', output)

    def test_tables_repeat_headers_and_code_is_escaped(self):
        source = '| Field | Value |\n|---|---|\n| A | B |\n\n```\n<script>alert(1)</script>\n```'
        output = markdown_to_html(source)
        self.assertIn('<thead>', output)
        self.assertIn('<td>B</td>', output)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', output)
        self.assertNotIn('<script>', output)
