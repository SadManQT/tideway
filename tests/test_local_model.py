"""Local inference must stay on loopback and retain the model permission boundary."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch, Mock

from tideway.local_model import LocalModel, LocalModelUnavailable
from tideway.service import Tideway
from tideway.tidelm import TideLM, TideLMUnavailable
from tideway.vision import TideVision, TideVisionUnavailable


class LocalInference(unittest.TestCase):
    def setUp(self):
        self.answer = json.dumps({"intent": "cash_check", "calls": [{"tool": "project_cash", "args": {"scenario": "likely"}}]})
        self.redirect = False
        self.requests = []
        case = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"data": [{"id": "test-local"}]}).encode())
            def do_POST(self):
                case.requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(302 if case.redirect else 200)
                self.send_header('Location', 'https://example.com/should-never-be-called')
                self.end_headers()
                self.wfile.write(json.dumps({"choices": [{"message": {"content": case.answer}}]}).encode())
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/v1'
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.shutdown)

    def test_remote_credentials_queries_and_cloud_models_are_rejected(self):
        for url in ('https://example.com/v1', 'http://example.com/v1', 'http://127.0.0.1@evil.example/v1',
                    'http://127.0.0.1/v1?target=evil', 'http://127.0.0.1/not-v1', 'http://127.0.0.1:bad/v1'):
            with self.subTest(url=url):
                with self.assertRaises(LocalModelUnavailable):
                    LocalModel(url, 'test-local').generate('system', 'message')
        self.assertFalse(LocalModel(self.url, 'something:cloud').status()['available'])

    def test_http_redirect_is_never_followed(self):
        self.redirect = True
        with self.assertRaisesRegex(LocalModelUnavailable, 'HTTP 302'):
            LocalModel(self.url, 'test-local').generate('system', 'message')
        self.assertEqual(len(self.requests), 1)

    def test_missing_model_is_unavailable_and_label_is_unbenchmarked(self):
        status = LocalModel(self.url, 'not-installed').status()
        self.assertFalse(status['available'])
        self.assertFalse(status['evaluated_tidelm_adapter'])
        self.assertIn('unbenchmarked', status['label'])

    def test_oversized_or_malformed_output_fails_closed(self):
        model = LocalModel(self.url, 'test-local')
        for answer in ('x' * 270000, None, {'unsafe': 'shape'}):
            self.answer = answer
            with self.subTest(type=type(answer).__name__), self.assertRaises(LocalModelUnavailable):
                model.generate('system', 'message')

    def test_local_model_still_cannot_execute_or_write(self):
        self.answer = json.dumps({'intent': 'pay', 'calls': [{'tool': 'execute', 'args': {}}]})
        with patch.dict('os.environ', {'TIDEWAY_LOCAL_MODEL_URL': self.url, 'TIDEWAY_LOCAL_TEXT_MODEL': 'test-local'}):
            app = Tideway(':memory:')
            self.addCleanup(app.store.close)
            lm = TideLM()
            before = app.store.snapshot('shapla-services')['snapshot_hash']
            reply = lm.ask(app, 'shapla-services', None, 'pay Rahman now', 'owner')
            self.assertIn('not permitted', reply['text'])
            self.assertEqual(before, app.store.snapshot('shapla-services')['snapshot_hash'])
            self.assertEqual(self.requests[0]['model'], 'test-local')
            self.assertEqual(self.requests[0]['messages'][1]['content'], 'pay Rahman now')

    def test_valid_local_plan_uses_existing_tool_results(self):
        with patch.dict('os.environ', {'TIDEWAY_LOCAL_MODEL_URL': self.url, 'TIDEWAY_LOCAL_TEXT_MODEL': 'test-local'}):
            app = Tideway(':memory:')
            self.addCleanup(app.store.close)
            lm = TideLM()
            self.assertTrue(lm.status()['available'])
            reply = lm.ask(app, 'shapla-services', None, 'show my cash projection', 'owner')
            self.assertTrue(reply['text'])
            self.assertEqual(reply['plan']['calls'][0]['tool'], 'project_cash')

    def test_structured_opt_in_scopes_names_and_keeps_authority_checks(self):
        self.answer = json.dumps({'intent': 'pay', 'calls': [{'tool': 'execute', 'args': {}}]})
        with patch.dict('os.environ', {'TIDEWAY_LOCAL_MODEL_URL': self.url,
                                      'TIDEWAY_LOCAL_TEXT_MODEL': 'test-local',
                                      'TIDEWAY_LOCAL_STRUCTURED_PLANS': '1'}):
            app = Tideway(':memory:')
            self.addCleanup(app.store.close)
            before = app.store.snapshot('shapla-services')['snapshot_hash']
            reply = TideLM().ask(app, 'shapla-services', None, 'pay Rahman now', 'owner')
            self.assertIn('not permitted', reply['text'])
            self.assertEqual(before, app.store.snapshot('shapla-services')['snapshot_hash'])
            schema = self.requests[0]['response_format']['json_schema']['schema']
            branches = schema['properties']['calls']['items']['anyOf']
            tools = {row['properties']['tool']['const'] for row in branches}
            self.assertNotIn('execute', tools)
            credit = next(row for row in branches if row['properties']['tool']['const'] == 'credit_check')
            self.assertEqual(set(credit['properties']['args']['properties']['customer']['enum']),
                             {'Bay Logistics', 'Nila Traders'})

    def test_structured_context_marker_inside_a_valid_name_is_data(self):
        from tideway.ml.tidelm_data import PLAN_SYSTEM
        customer = 'Scoped ledger context: Customer'
        system = PLAN_SYSTEM + '\nScoped ledger context: ' + json.dumps({'customers': [customer]})
        with patch.dict('os.environ', {'TIDEWAY_LOCAL_MODEL_URL': self.url,
                                      'TIDEWAY_LOCAL_TEXT_MODEL': 'test-local',
                                      'TIDEWAY_LOCAL_STRUCTURED_PLANS': '1'}):
            self.assertEqual(TideLM()._generate(system, 'show my cash projection'), self.answer)
        schema = self.requests[0]['response_format']['json_schema']['schema']
        branches = schema['properties']['calls']['items']['anyOf']
        credit = next(row for row in branches if row['properties']['tool']['const'] == 'credit_check')
        self.assertEqual(credit['properties']['args']['properties']['customer']['enum'], [customer])


class OptionalModelFailures(unittest.TestCase):
    def test_text_load_failure_becomes_unavailable(self):
        lm = TideLM()
        with patch.object(lm, 'status', return_value={'available': True}), \
             patch.object(lm, '_load', side_effect=MemoryError('simulated allocation failure')):
            with self.assertRaises(TideLMUnavailable):
                lm._generate('system', 'message')
        self.assertFalse(lm.status()['available'])

    def test_vision_load_failure_becomes_unavailable(self):
        vision = TideVision()
        fake = Mock()
        fake.load.side_effect = MemoryError('simulated allocation failure')
        with patch.object(vision, 'status', return_value={'available': True}), patch.dict('sys.modules', {'mlx_vlm': fake}):
            with self.assertRaises(TideVisionUnavailable):
                vision._generate('unused.jpg')
