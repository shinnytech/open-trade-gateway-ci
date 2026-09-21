"""执行外部工作流的来源核验，覆盖 PR head 与合并提交不同的情形。"""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/otg-go-arm64.yml'


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = dict(request_id='c' * 32, source_sha='a' * 40, version='2.3.14',
                            upstream_run_id='123', upstream_run_attempt='1')
        self.run = dict(path='.github/workflows/release-payload.yml', event='pull_request_target',
                        run_attempt=1, head_sha='b' * 40)
        self.pr = dict(merged_at='2026-09-21T00:00:00Z', merge_commit_sha='a' * 40,
                       base=dict(ref='master', repo=dict(full_name='shinnytech/otg-go')),
                       head=dict(sha='b' * 40))
        text = WORKFLOW.read_text().split("python3 - <<'PYCODE'\n", 1)[1].split('          PYCODE\n', 1)[0]
        self.script = textwrap.dedent(text)

    def verify(self):
        event, output = self.root / 'event.json', self.root / 'output'
        event.write_text(json.dumps(dict(client_payload=self.payload)))
        def open_url(request, timeout):
            self.assertEqual(timeout, 30)
            if request.full_url.endswith('/actions/runs/123'):
                data = self.run
            else:
                self.assertTrue(request.full_url.endswith('/commits/' + self.payload['source_sha'] + '/pulls'))
                data = [self.pr]
            return contextlib.closing(io.BytesIO(json.dumps(data).encode()))
        with patch.dict(os.environ, GITHUB_EVENT_PATH=str(event), GITHUB_OUTPUT=str(output), GH_TOKEN='fixture'), patch('urllib.request.urlopen', open_url):
            exec(compile(self.script, str(WORKFLOW), 'exec'), {})
        result = dict(line.split('=', 1) for line in output.read_text().splitlines())
        self.assertEqual(result['source_sha'], self.payload['source_sha'])
        self.assertEqual(result['version'], self.payload['version'])
        self.assertEqual(result['source_event'], self.run['event'])

    def test_accepts_master_merge_separate_from_pr_head(self):
        self.verify()

    def test_rejects_pr_head_as_release_commit(self):
        self.payload['source_sha'] = self.run['head_sha']
        with self.assertRaisesRegex(SystemExit, 'master merge'):
            self.verify()

    def test_rejects_unmerged_pr_or_wrong_base(self):
        for field in ('merged', 'base'):
            with self.subTest(field=field):
                self.pr['merged_at'] = None if field == 'merged' else '2026-09-21T00:00:00Z'
                self.pr['base']['ref'] = 'other' if field == 'base' else 'master'
                with self.assertRaisesRegex(SystemExit, 'master merge'):
                    self.verify()

    def test_accepts_matching_tag_and_rejects_mismatch(self):
        self.run['event'], self.run['head_sha'] = 'push', self.payload['source_sha']
        self.verify()
        self.run['head_sha'] = 'd' * 40
        with self.assertRaisesRegex(SystemExit, 'tag run'):
            self.verify()

    def test_rejects_unrelated_run_or_attempt(self):
        for key, value in [('path', '.github/workflows/ci.yml'), ('event', 'pull_request'), ('run_attempt', 2)]:
            with self.subTest(key=key), patch.dict(self.run, {key:value}):
                with self.assertRaisesRegex(SystemExit, 'upstream release run'):
                    self.verify()

    def test_rejects_injected_fields(self):
        self.payload['version'] = '2.3.14\ninjected'
        with self.assertRaisesRegex(SystemExit, 'invalid dispatch field'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
