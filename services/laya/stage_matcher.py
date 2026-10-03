"""Fetch one pinned model release and write a checksum lock; never used by requests."""
from pathlib import Path
import hashlib, json
from huggingface_hub import hf_hub_download
ROOT = Path(__file__).resolve().parent / 'models' / 'multilingual-e5-small'
REV = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
EXPECTED = {'model.safetensors':'1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477', 'tokenizer.json':'0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39', 'sentencepiece.bpe.model':'cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865'}
ROOT.mkdir(parents=True, exist_ok=True)
files = {}
for name in [*EXPECTED, 'config.json', 'tokenizer_config.json', 'special_tokens_map.json']:
    path = Path(hf_hub_download('intfloat/multilingual-e5-small', name, revision=REV, local_dir=ROOT))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if name in EXPECTED and sha != EXPECTED[name]: raise ValueError('checksum mismatch')
    files[name] = sha
    print(name + ' verified', flush=True)
lock = {'model_id':'intfloat/multilingual-e5-small', 'revision':REV, 'files_sha256':files, 'dimension':384, 'max_tokens':512, 'pooling':'masked_mean_l2', 'query_prefix':'query: ', 'passage_prefix':'passage: ', 'query_template_version':'qris-merchant-city-whole-rupiah-1'}
Path(__file__).with_name('matcher-release.json').write_text(json.dumps(lock, indent=2)+'\n')
