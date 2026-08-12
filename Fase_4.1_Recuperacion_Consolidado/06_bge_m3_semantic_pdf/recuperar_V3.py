"""Recuperacion V3 independiente para BGE-M3 de PDF semantico."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any
import faiss
from sentence_transformers import CrossEncoder,SentenceTransformer
MODEL_NAME="BAAI/bge-m3"; RERANKER_NAME="BAAI/bge-reranker-v2-m3"; FOLDER=Path(__file__).resolve().parent; NEAR_DUPLICATE_THRESHOLD=0.90
def read_metadata(path:Path)->list[dict[str,Any]]:
    records=[]
    with path.open("r",encoding="utf-8") as handle:
        for number,line in enumerate(handle,1):
            if line.strip():
                value=json.loads(line)
                if not isinstance(value,dict): raise ValueError(f"Metadata invalida: {path}:{number}")
                records.append(value)
    return records
def allowed(record,score,args): return score>=args.threshold and (args.fenomeno is None or str(record.get("fenomeno"))==str(args.fenomeno)) and (not args.idioma or str(record.get("idioma","")).lower()==args.idioma.lower()) and (not args.formato or str(record.get("formato","")).lower()==args.formato.lower())
def text_key(text): return " ".join(str(text or "").casefold().split())
def normalize(values):
    low,high=min(values),max(values); return [1.0]*len(values) if low==high else [(value-low)/(high-low) for value in values]
def deduplicate(scored,vectors,args):
    order=sorted(range(len(scored)),key=lambda i:(-scored[i][0],scored[i][1][0])); kept=[]; exact=set()
    for i in order:
        score,(recall_rank,record)=scored[i]; chunk_id=record.get("chunk_id"); text=text_key(record.get("texto"))
        if chunk_id in exact or (text and text in exact) or any(float(vectors[i]@vectors[j])>=args.near_duplicate_threshold for j in kept): continue
        kept.append(i); exact.update(key for key in (chunk_id,text) if key)
    return [(scored[i],vectors[i]) for i in kept]
def select_mmr(scored,vectors,args):
    scores=[item[0] for item in scored]; relevance=normalize(scores); ranked=sorted(range(len(scored)),key=lambda i:(-scores[i],scored[i][1][0])); selected=[]; remaining=set(ranked)
    while remaining and len(selected)<args.output_top_k:
        best=max(remaining,key=lambda i:(args.mmr_lambda*relevance[i]-(1-args.mmr_lambda)*(max(float(vectors[i]@vectors[j]) for j in selected) if selected else 0.0),-ranked.index(i))); selected.append(best); remaining.remove(best)
    return [(scores[i],scored[i][1][1]) for i in selected]
def retrieve(question,encoder,reranker,index,records,args):
    if not question.strip(): raise ValueError("La pregunta no puede estar vacia.")
    query=encoder.encode([question],convert_to_numpy=True,normalize_embeddings=True,show_progress_bar=False).astype("float32"); scores,positions=index.search(query,min(args.recall_top_k,index.ntotal)); candidates=[(rank,float(score),records[int(pos)]) for rank,(score,pos) in enumerate(zip(scores[0],positions[0]),1) if 0<=pos<len(records) and allowed(records[int(pos)],float(score),args)]
    if candidates:
        texts=[record.get("texto","") for _,_,record in candidates]; values=[float(value) for value in reranker.predict([(question,text) for text in texts],show_progress_bar=False)]; vectors=encoder.encode(texts,convert_to_numpy=True,normalize_embeddings=True,show_progress_bar=False); scored=[(values[i],(candidates[i][0],candidates[i][2])) for i in range(len(candidates))]; unique=deduplicate(scored,vectors,args); final=select_mmr([item for item,_ in unique],[vector for _,vector in unique],args) if unique else []
    else: final=[]
    grouped={}
    for score,record in final: grouped.setdefault(record.get("doc_id"),[]).append(score)
    docs=sorted(grouped,key=lambda doc:-sum(grouped[doc])/len(grouped[doc]))[:3]; documents=[{"rank":rank,"doc_id":doc,"score":sum(grouped[doc])/len(grouped[doc])} for rank,doc in enumerate(docs,1)]; fragments=[{"rank":rank,"chunk_id":record.get("chunk_id"),"doc_id":record.get("doc_id"),"text":record.get("texto",""),"score":score,"fuente":record.get("fuente"),"fenomeno":record.get("fenomeno"),"idioma":record.get("idioma")} for rank,(score,record) in enumerate(final,1)]
    return {"query_id":"q001","query":question,"documents":documents,"fragments":fragments}
def load_questions(path):
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,list): raise ValueError("El archivo de preguntas debe contener un arreglo JSON.")
    result=[]
    for number,item in enumerate(value,1):
        if isinstance(item,str): result.append((f"q{number:03d}",item))
        elif isinstance(item,dict) and isinstance(item.get("query"),str): result.append((str(item.get("query_id",f"q{number:03d}")),item["query"]))
        else: raise ValueError(f"La pregunta {number} debe tener el campo 'query'.")
    return result
def main():
    parser=argparse.ArgumentParser(description="Recuperacion BGE-M3 PDF semantico V3 independiente."); parser.add_argument("--query"); parser.add_argument("--questions",type=Path,help="Archivo JSON con un arreglo de preguntas."); parser.add_argument("--recall-top-k",type=int,default=50); parser.add_argument("--output-top-k",type=int,default=10); parser.add_argument("--model",default=MODEL_NAME); parser.add_argument("--reranker-model",default=RERANKER_NAME); parser.add_argument("--mmr-lambda",type=float,default=0.7); parser.add_argument("--near-duplicate-threshold",type=float,default=NEAR_DUPLICATE_THRESHOLD); parser.add_argument("--device",default=None); parser.add_argument("--index",type=Path,default=FOLDER/"index.faiss"); parser.add_argument("--metadata",type=Path,default=FOLDER/"metadata.jsonl"); parser.add_argument("--output-json",type=Path,default=FOLDER/"resultado_v3.json"); parser.add_argument("--output",type=Path); parser.add_argument("--threshold",type=float,default=-1.0); parser.add_argument("--fenomeno",type=int,choices=(1,2,3)); parser.add_argument("--idioma"); parser.add_argument("--formato"); args=parser.parse_args()
    if args.recall_top_k<1 or args.output_top_k<1 or not 0<=args.mmr_lambda<=1 or not 0<=args.near_duplicate_threshold<=1: raise ValueError("Parametros invalidos.")
    if not args.index.exists() or not args.metadata.exists(): raise FileNotFoundError("No existe el indice o la metadata.")
    index,records=faiss.read_index(str(args.index)),read_metadata(args.metadata)
    if index.ntotal!=len(records): raise ValueError("El indice y la metadata no coinciden.")
    if args.query and args.questions: raise ValueError("Usa --query o --questions, no ambos.")
    encoder,reranker=SentenceTransformer(args.model,device=args.device),CrossEncoder(args.reranker_model,device=args.device); questions=[("q001",args.query)] if args.query else (load_questions(args.questions) if args.questions else None); output_handle=args.output.open("w",encoding="utf-8") if args.output else None; results=[]
    try:
        if questions is None: questions=iter(lambda:("q001",input("Pregunta> ")),("q001","salir"))
        for number,(query_id,question) in enumerate(questions,1):
            result=retrieve(question,encoder,reranker,index,records,args); result["query_id"]=query_id; results.append(result); print(json.dumps(result,ensure_ascii=False)); output_handle.write(json.dumps(result,ensure_ascii=False)+"\n") if output_handle else None
    except EOFError: pass
    finally:
        if output_handle: output_handle.close()
    args.output_json.write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":
    try: main()
    except (FileNotFoundError,ValueError,ImportError,json.JSONDecodeError) as exc: print(f"Error: {exc}",file=sys.stderr); raise SystemExit(1)
