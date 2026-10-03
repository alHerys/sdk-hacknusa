"""Synthetic retrieval benchmark through actual authenticated HTTP, no private data."""
import json, time, statistics
from pathlib import Path
from http.client import HTTPConnection
from service import canonical, digest

def main():
    token=Path(__file__).with_name('.env').read_text().strip().partition('=')[2]
    cases=[
      ('clear-merchant', 'KOPI BUDI', ['Bayar pesanan ke KOPI BUDI pakai QRIS.', 'Besok rapat jam 9','Transfer uang ke TOKO JAYA','Makan di rumah'], {'0'}),
      ('indonesian-slang','WARUNG SARI',['Bro bayar ke warung sari ya, 35rb pake qris','Gw udah balik rumah','TF ke Budi 50rb','Nanti ketemu kantor'],{'0'}),
      ('separate-message','TOKO JAYA',['Bayar barangnya ke TOKO JAYA ya','Ini gambar QR nya','KOPI BUDI buka jam 8','Tiket sudah dikirim'],{'0'}),
      ('same-merchant-other-chat','KOPI BUDI',['Bayar pesanan ke KOPI BUDI pakai QRIS.','Bayar pesanan ke KOPI BUDI pakai QRIS.','Jadwal rapat','Bukan pembayaran'],{'0','1'}),
      ('correction','WARUNG SARI',['Jadi bayarnya ke warung sari, bukan toko jaya','Toko jaya belum buka','Rapat dimulai besok','KOPI BUDI habis'],{'0'}),
      ('no-relevant-context','KOPI BUDI',['Besok rapat jam 9','Kucing lagi tidur','Jadwal kereta sore','Film itu menarik'],set()),
      ('same-name-ambiguity','TOKO JAYA',['Toko Jaya di chat A minta bayar','Toko Jaya di chat B minta bayar','Bayar ke WARUNG SARI','Kopi habis'],{'0','1'}),
      ('numeric-context','BAKSO MAJU',['Bayar bakso maju 25rb qris ya','25rb untuk kopi budi','Sudah jam 25?','Besok ketemu'],{'0'}),
    ]
    rows=[]
    for name,merchant,texts,relevant in cases:
        request={'schema_version':'1.0','request_id':'benchmark-'+name,'profile':'qris_artifact_context','snapshot_digest':digest({'case':name}),'deadline_unix_ms':int(time.time()*1000)+30000,'processing_permissions':{'matching_local':True},'qr':{'merchant':merchant,'city':'JAKARTA','amount_minor':25000},'candidates':[{'candidate_id':str(i),'text':text} for i,text in enumerate(texts)]}
        conn=HTTPConnection('127.0.0.1',8765,timeout=31);start=time.monotonic()
        try:
            conn.request('POST','/v1/context-match',canonical(request),{'Content-Type':'application/json','Authorization':'Bearer '+token})
            response=conn.getresponse();result=json.loads(response.read());assert response.status==200,result
        finally:conn.close()
        assert result['request_id']==request['request_id'] and result['snapshot_digest']==request['snapshot_digest']
        ids=[s['candidate_id'] for s in result['suggestions']]
        rows.append({'case':name,'relevant_ids':sorted(relevant),'suggestions':result['suggestions'],'top_1_hit':bool(ids and ids[0] in relevant) if relevant else None,'top_3_hit':bool(set(ids)&relevant) if relevant else None,'latency_ms':round((time.monotonic()-start)*1000,1)})
    # Actual model token overflow, oversized UTF-16 and deterministic tie order.
    request['request_id']='benchmark-limits';request['deadline_unix_ms']=int(time.time()*1000)+30000
    request['candidates']=[{'candidate_id':'tie1','text':'bayar bakso maju'},{'candidate_id':'tie2','text':'bayar bakso maju'},{'candidate_id':'overflow','text':'x '*2000},{'candidate_id':'oversized','text':'😀'*2049}]
    conn=HTTPConnection('127.0.0.1',8765,timeout=31)
    try:
        conn.request('POST','/v1/context-match',canonical(request),{'Content-Type':'application/json','Authorization':'Bearer '+token});response=conn.getresponse();result=json.loads(response.read());assert response.status==200
    finally:conn.close()
    assert [s['candidate_id'] for s in result['suggestions']]==['tie1','tie2']
    assert {s['candidate_id']:s['reason'] for s in result['skipped']}=={'overflow':'token_overflow','oversized':'oversized'}
    positives=[r for r in rows if r['relevant_ids']]
    latency=sorted(r['latency_ms'] for r in rows)
    report={'status':'passed','dataset':'eight synthetic Indonesian cases; seven have relevant context; no training or tuning','matcher_fingerprint':result['matcher_fingerprint'],'top_1':sum(r['top_1_hit'] for r in positives)/len(positives),'top_3':sum(r['top_3_hit'] for r in positives)/len(positives),'latency_median_ms':statistics.median(latency),'latency_max_ms':max(latency),'rows':rows,'token_oversize_stable_ties':'passed','interpretation':'No-match and duplicate-chat cases demonstrate that ranking never authenticates association. No threshold or payment safety claim.'}
    Path(__file__).with_name('matcher-benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
if __name__=='__main__':main()
