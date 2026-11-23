import importlib.util
import tempfile
import unittest
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / 'distribution' / 'review' / 'review.py'
SPEC = importlib.util.spec_from_file_location('review_edition', PATH)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


class ReviewEditionTests(unittest.TestCase):
    def test_snapshot_keeps_only_eligible_source(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = root / 'src'
            source.mkdir()
            (source / 'app.py').write_text('pass\n', encoding='utf-8')
            (source / 'secret.py').write_text('pass\n', encoding='utf-8')
            (source / 'report.json').write_text('{}', encoding='utf-8')
            destination = root / 'snapshot'
            destination.mkdir()
            self.assertEqual(REVIEW.snapshot(source, destination), (1, 2))
            self.assertEqual([p.name for p in destination.iterdir()], ['app.py'])

    def test_review_report_discards_raw_source_and_marks_partial(self):
        document = {'results': [{'test_id': 'B501', 'filename': './app.py',
                                 'line_number': 7, 'code': 'private-source-marker'}],
                    'errors': [{'reason': 'private-error-marker'}], 'metrics': {'./app.py': {}}}
        report = REVIEW.format_result(document, 2, 0)
        self.assertIn('部分文件', report)
        self.assertIn('app.py:7', report)
        self.assertNotIn('private-', report)


if __name__ == '__main__':
    unittest.main()
