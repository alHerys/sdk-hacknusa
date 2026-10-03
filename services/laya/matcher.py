"""Pinned offline E5 retrieval. Similarity is not message authentication."""
from pathlib import Path
import hashlib, importlib.metadata, math, platform
from concurrent.futures import TimeoutError as FutureTimeout
import time
from service import canonical, decode_json, digest, _keys, _text, InputError, REQUEST_ID, SHA256, SCHEMA, MAX_DEADLINE_MS


def validate_match(request, now_ms=None):
    _keys(request, ('schema_version','request_id','profile','snapshot_digest','deadline_unix_ms','processing_permissions','qr','candidates'))
    if request['schema_version'] != SCHEMA or request['profile'] != 'qris_artifact_context': raise InputError('unsupported_schema_or_profile')
    if not isinstance(request['request_id'], str) or not REQUEST_ID.fullmatch(request['request_id']): raise InputError('invalid_request_id')
    if not isinstance(request['snapshot_digest'], str) or not SHA256.fullmatch(request['snapshot_digest']): raise InputError('invalid_snapshot_digest')
    deadline = request['deadline_unix_ms']
    if type(deadline) is not int: raise InputError('invalid_deadline')
    remaining = deadline - (int(time.time()*1000) if now_ms is None else now_ms)
    if remaining > MAX_DEADLINE_MS: raise InputError('deadline_too_far')
    _keys(request['processing_permissions'], ('matching_local',))
    if request['processing_permissions']['matching_local'] is not True: raise InputError('matching_permission_required')
    qr = request['qr']; _keys(qr, ('merchant','city','amount_minor')); _text(qr['merchant'])
    if qr['city'] is not None: _text(qr['city'])
    amount = qr['amount_minor']
    if amount is not None and (type(amount) is not int or not 0 < amount <= 9223372036854775807): raise InputError('amount_must_be_positive_whole_rupiah_or_null')
    candidates = request['candidates']
    if not isinstance(candidates, list) or not 0 <= len(candidates) <= 20: raise InputError('candidate_limit')
    ids = set()
    for candidate in candidates:
        _keys(candidate, ('candidate_id','text'))
        cid = candidate['candidate_id']
        if not isinstance(cid,str) or not REQUEST_ID.fullmatch(cid) or cid in ids: raise InputError('invalid_candidate_id')
        ids.add(cid)
        # Oversized/absent candidates get structured skips rather than hidden cuts.
        if not isinstance(candidate['text'],str): raise InputError('invalid_candidate_text')
        try: candidate['text'].encode('utf-16-le')
        except UnicodeError as error: raise InputError('invalid_unicode') from error
    return time.monotonic() + remaining / 1000


def query_text(qr):
    text = 'Permintaan pembayaran QRIS kepada merchant ' + qr['merchant']
    if qr['city'] is not None: text += ' di kota ' + qr['city']
    if qr['amount_minor'] is not None: text += ' sebesar ' + str(qr['amount_minor']) + ' rupiah'
    return text + '.'


class E5Runner:
    def __init__(self, descriptor_path=None):
        path = descriptor_path or Path(__file__).with_name('matcher-release.json')
        lock = decode_json(path.read_bytes())
        if lock['model_id'] != 'intfloat/multilingual-e5-small' or lock['revision'] != '614241f622f53c4eeff9890bdc4f31cfecc418b3': raise ValueError('matcher release')
        if (lock['dimension'],lock['max_tokens'],lock['pooling'],lock['query_prefix'],lock['passage_prefix']) != (384,512,'masked_mean_l2','query: ','passage: '): raise ValueError('matcher configuration')
        folder = path.parent / 'models' / 'multilingual-e5-small'
        for name, expected in lock['files_sha256'].items():
            if name not in {'config.json','tokenizer_config.json','tokenizer.json','special_tokens_map.json','model.safetensors','sentencepiece.bpe.model'}: raise ValueError('unexpected matcher file')
            if hashlib.sha256((folder/name).read_bytes()).hexdigest() != expected: raise ValueError('matcher checksum')
        if not {'config.json','tokenizer_config.json','tokenizer.json','model.safetensors'}.issubset(lock['files_sha256']): raise ValueError('incomplete matcher release')
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True)
        self.model = AutoModel.from_pretrained(folder, local_files_only=True).to('cpu').eval()
        self.lock = lock
        self.fingerprint = digest({'release':lock, 'runtime':{n:importlib.metadata.version(n) for n in ('torch','transformers','tokenizers','numpy','safetensors')}, 'python':platform.python_version(), 'platform':platform.platform(), 'source':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'batch_size':4, 'device':'cpu', 'dtype':'float32', 'threads':torch.get_num_threads(), 'interop_threads':torch.get_num_interop_threads()})
        smoke = self.encode(['query: pembayaran QRIS Kopi Budi', 'passage: bayar QRIS Kopi Budi'])
        if smoke.shape != (2,384) or not torch.isfinite(smoke).all() or not torch.allclose(smoke.norm(dim=1), torch.ones(2), atol=1e-5): raise ValueError('matcher smoke')

    def token_count(self, text):
        return len(self.tokenizer(text, truncation=False, add_special_tokens=True)['input_ids'])

    def encode(self, texts):
        if len(texts) > 4: raise ValueError('batch limit')
        inputs = self.tokenizer(texts, padding=True, truncation=False, return_tensors='pt')
        if inputs['input_ids'].shape[1] > 512: raise ValueError('token limit')
        with self.torch.inference_mode():
            states = self.model(**inputs).last_hidden_state
            mask = inputs['attention_mask'].unsqueeze(-1).to(states.dtype)
            vectors = (states * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
            return self.torch.nn.functional.normalize(vectors, p=2, dim=1)

    def match(self, qr, candidates, cutoff):
        query = self.lock['query_prefix'] + query_text(qr)
        if self.token_count(query) > 512: raise ValueError('query_token_overflow')
        accepted, skipped = [], []
        for c in candidates:
            reason = 'absent' if not c['text'].strip() else 'oversized' if len(c['text'].encode('utf-16-le'))//2 > 4096 else 'token_overflow' if self.token_count(self.lock['passage_prefix'] + c['text']) > 512 else None
            if reason: skipped.append({'candidate_id':c['candidate_id'], 'reason':reason})
            else: accepted.append(c)
        if time.monotonic() >= cutoff: raise FutureTimeout()
        if not accepted: return {'suggestions':[], 'skipped':skipped}
        q = self.encode([query])[0]
        scored = []
        for offset in range(0, len(accepted), 4):
            if time.monotonic() >= cutoff: raise FutureTimeout()
            batch = accepted[offset:offset+4]
            vectors = self.encode([self.lock['passage_prefix']+c['text'] for c in batch])
            for candidate, vector in zip(batch, vectors):
                score = float(self.torch.dot(q, vector))
                if not math.isfinite(score): raise ValueError('nonfinite cosine')
                scored.append({'candidate_id':candidate['candidate_id'], 'cosine':score})
        # Python stable sort preserves input order for exact ties.
        scored.sort(key=lambda item: -item['cosine'])
        return {'suggestions':scored[:3], 'skipped':skipped}


def context_match(service, request):
    cutoff = validate_match(request)
    frozen = decode_json(canonical({'qr':request['qr'],'candidates':request['candidates']}))
    runner = service.matcher
    envelope = {'schema_version':SCHEMA, 'request_id':request['request_id'], 'profile':request['profile'], 'snapshot_digest':request['snapshot_digest'], 'input_digest':digest(frozen), 'matcher_fingerprint':runner.fingerprint if runner else None, 'status':'unavailable', 'unavailable_reason':None, 'suggestions':[], 'skipped':[]}
    def fail(status, reason): return status, {**envelope, 'unavailable_reason':reason}
    if time.monotonic() >= cutoff: return fail(408,'deadline_exceeded')
    if runner is None: return fail(503,'matcher_unavailable')
    if not service.slots.acquire(blocking=False): return fail(503,'busy')
    def invoke():
        if time.monotonic() >= cutoff: raise FutureTimeout()
        result = runner.match(frozen['qr'], frozen['candidates'], cutoff)
        if time.monotonic() >= cutoff: raise FutureTimeout()
        return result
    try: future = service.executor.submit(invoke)
    except Exception:
        service.slots.release(); return fail(503,'worker_unavailable')
    future.add_done_callback(lambda _:service.slots.release())
    try:
        result = future.result(timeout=max(0, cutoff-time.monotonic()))
        return 200, {**envelope, **result, 'status':'experimental'}
    except FutureTimeout: return fail(408,'deadline_exceeded')
    except Exception: return fail(503,'matcher_unavailable')
