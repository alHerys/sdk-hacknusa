import unittest, time, threading
from http.client import HTTPConnection
from service import SemanticService, LocalServer, canonical, digest, InputError
from test_service import FakeRunner, request as semantic_request
from matcher import validate_match, query_text

def request(candidates=None):
    return {'schema_version':'1.0','request_id':'match-test','profile':'qris_artifact_context','snapshot_digest':'a'*64,'deadline_unix_ms':int(time.time()*1000)+30000,'processing_permissions':{'matching_local':True},'qr':{'merchant':'BUDI STORE','city':'JAKARTA','amount_minor':350000},'candidates':candidates or [{'candidate_id':'one','text':'bayar'}]}
class FakeMatcher:
    fingerprint='b'*64
    def match(self,qr,candidates,cutoff):
        return {'suggestions':[{'candidate_id':c['candidate_id'],'cosine':.9} for c in candidates[:3]],'skipped':[]}
class MatcherTests(unittest.TestCase):
    def test_permission_ids_limits_and_native_qr_money(self):
        r=request();validate_match(r)
        self.assertIn('350000 rupiah',query_text(r['qr']))
        for change in ({'processing_permissions':{'matching_local':False}}, {'candidates':[{'candidate_id':'one','text':'a'},{'candidate_id':'one','text':'b'}]}, {'candidates':[{'candidate_id':str(i),'text':'a'} for i in range(21)]}, {'qr':{'merchant':'BUDI','city':None,'amount_minor':True}}):
            with self.assertRaises(InputError):validate_match({**r,**change})
    def test_correlation_and_missing_model_independent_of_semantic(self):
        service=SemanticService(FakeRunner(),matcher=FakeMatcher())
        try:
            r=request();status,result=service.find_context(r)
            self.assertEqual(200,status);self.assertEqual(r['snapshot_digest'],result['snapshot_digest'])
            self.assertEqual(digest({'qr':r['qr'],'candidates':r['candidates']}),result['input_digest'])
            service.matcher=None;self.assertEqual(503,service.find_context(r)[0])
            self.assertEqual(200,service.assess(semantic_request())[0])
        finally:service.close()
    def test_native_timeout_keeps_shared_capacity(self):
        start,finish=threading.Event(),threading.Event()
        class Blocking(FakeMatcher):
            def match(self,*args):start.set();finish.wait(1);return super().match(*args)
        service=SemanticService(FakeRunner(),capacity=1,matcher=Blocking())
        try:
            r=request();r['deadline_unix_ms']=int(time.time()*1000)+30
            self.assertEqual(408,service.find_context(r)[0]);self.assertTrue(start.is_set())
            self.assertEqual(503,service.assess(semantic_request())[0])
        finally:finish.set();service.close()
    def test_actual_http_endpoint_auth_and_distinct_body_limits(self):
        service=SemanticService(FakeRunner(),matcher=FakeMatcher())
        server=LocalServer(('127.0.0.1',0),service,'t'*32)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def send(path,data,auth=True):
            connection=HTTPConnection(*server.server_address,timeout=3)
            try:
                connection.request('POST',path,data,{'Content-Type':'application/json',**({'Authorization':'Bearer '+'t'*32} if auth else {})})
                response=connection.getresponse();body=response.read();return response.status,body
            finally:connection.close()
        try:
            body=canonical(request([{'candidate_id':str(i),'text':'x'*4096} for i in range(20)]))
            self.assertGreater(len(body),32768)
            self.assertEqual(200,send('/v1/context-match',body)[0]);self.assertEqual(413,send('/v1/semantic',body)[0])
            self.assertEqual(401,send('/v1/context-match',body,False)[0]);self.assertEqual(413,send('/v1/context-match',b'x'*524289)[0])
        finally:server.shutdown();server.server_close();service.close();thread.join()
