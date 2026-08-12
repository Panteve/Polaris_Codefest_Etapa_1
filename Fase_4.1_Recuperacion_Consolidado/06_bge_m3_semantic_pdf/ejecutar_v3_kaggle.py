"""Celda Kaggle completa para el corpus 06."""
# Dependencias, si hacen falta:
# !pip install -q faiss-cpu sentence-transformers

from pathlib import Path
import json
import faiss
from sentence_transformers import CrossEncoder, SentenceTransformer

INPUT=Path('/kaggle/input'); OUTPUT=Path('/kaggle/working'); HINT='06_bge_m3_semantic_pdf'
RECALL_TOP_K=100; OUTPUT_TOP_K=10; BATCH_SIZE=8; MMR_LAMBDA=.7; DUP_THRESHOLD=.90
MODEL='BAAI/bge-m3'; RERANKER='BAAI/bge-reranker-v2-m3'; QUESTIONS='ground_truth_15_preguntas.json'

def files(name): return sorted(p for p in INPUT.rglob(name) if p.is_file())
def locate():
    pairs=[(i,m) for i in files('index.faiss') for m in files('metadata.jsonl') if i.parent==m.parent]
    if not pairs: raise FileNotFoundError('No se encontro index.faiss junto a metadata.jsonl.')
    pair=([p for p in pairs if HINT.casefold() in str(p[0].parent).casefold()] or pairs)[0]; print('index:',pair[0]); print('metadata:',pair[1]); return pair
def question_file():
    found=files(QUESTIONS)
    if not found: raise FileNotFoundError(f'No se encontro {QUESTIONS}.')
    return found[0]
def metadata(path):
    with path.open(encoding='utf-8') as f: return [json.loads(x) for x in f if x.strip()]
def questions(path): return [(str(x.get('query_id',f'q{n:03d}')),x['query']) for n,x in enumerate(json.loads(path.read_text(encoding='utf-8')),1)]
def norm(x):
    lo,hi=min(x),max(x); return [1.0]*len(x) if lo==hi else [(v-lo)/(hi-lo) for v in x]
def run(q,qn,total,enc,rer,index,recs):
    print(f'Pregunta {qn}/{total} - inicio: 0%'); v=enc.encode([q],convert_to_numpy=True,normalize_embeddings=True).astype('float32'); s,pos=index.search(v,min(RECALL_TOP_K,index.ntotal)); print(f'Pregunta {qn}/{total} - recall: 25%'); cand=[(r,float(sc),recs[int(p)]) for r,(sc,p) in enumerate(zip(s[0],pos[0]),1) if 0<=p<len(recs)]; print(f'Pregunta {qn}/{total} - filtros: 40%'); texts=[x[2].get('texto','') for x in cand]; rs=[]; vec=[]
    for a in range(0,len(texts),BATCH_SIZE):
        b=texts[a:a+BATCH_SIZE]; rs += [float(x) for x in rer.predict([(q,t) for t in b],show_progress_bar=False)]; z=min(a+len(b),len(texts)); print(f'Pregunta {qn}/{total} - reranking chunks: {z*100//len(texts)}% ({z}/{len(texts)})'); vec += list(enc.encode(b,convert_to_numpy=True,normalize_embeddings=True,show_progress_bar=False)); print(f'Pregunta {qn}/{total} - embeddings MMR: {z*100//len(texts)}% ({z}/{len(texts)})')
    scored=[(rs[i],cand[i][0],cand[i][2],vec[i]) for i in range(len(cand))]; keep=[]; exact=set()
    for i in sorted(range(len(scored)),key=lambda i:(-scored[i][0],scored[i][1])):
        x=scored[i]; key=' '.join(str(x[2].get('texto','')).casefold().split()); cid=x[2].get('chunk_id')
        if cid in exact or (key and key in exact) or any(float(x[3]@scored[j][3])>=DUP_THRESHOLD for j in keep): continue
        keep.append(i); exact.update(k for k in (cid,key) if k)
    print(f'Pregunta {qn}/{total} - deduplicacion: 75%'); u=[scored[i] for i in keep]; rel=norm([x[0] for x in u]) if u else []; rank=sorted(range(len(u)),key=lambda i:(-u[i][0],u[i][1])); selected=[]; rem=set(rank)
    while rem and len(selected)<OUTPUT_TOP_K:
        best=max(rem,key=lambda i:(MMR_LAMBDA*rel[i]-(1-MMR_LAMBDA)*(max(float(u[i][3]@u[j][3]) for j in selected) if selected else 0),-rank.index(i))); selected.append(best); rem.remove(best)
    print(f'Pregunta {qn}/{total} - MMR: 90%'); final=[(u[i][0],u[i][2]) for i in selected]; groups={}
    for sc,r in final: groups.setdefault(r.get('doc_id'),[]).append(sc)
    docs=sorted(groups,key=lambda d:-sum(groups[d])/len(groups[d]))[:3]; documents=[{'rank':n,'doc_id':d,'score':sum(groups[d])/len(groups[d])} for n,d in enumerate(docs,1)]; fragments=[{'rank':n,'chunk_id':r.get('chunk_id'),'doc_id':r.get('doc_id'),'text':r.get('texto',''),'score':sc,'fuente':r.get('fuente'),'fenomeno':r.get('fenomeno'),'idioma':r.get('idioma')} for n,(sc,r) in enumerate(final,1)]; print(f'Pregunta {qn}/{total} - listo: 100%'); return {'query_id':'q001','query':q,'documents':documents,'fragments':fragments}
def main():
    ip,mp=locate(); recs=metadata(mp); qs=questions(question_file()); index=faiss.read_index(str(ip)); assert index.ntotal==len(recs); enc=SentenceTransformer(MODEL); rer=CrossEncoder(RERANKER); out=[]
    for n,(qid,q) in enumerate(qs,1): r=run(q,n,len(qs),enc,rer,index,recs); r['query_id']=qid; out.append(r)
    path=OUTPUT/'resultado_v3_preguntas.json'; path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print('Resultado:',path)
main()
