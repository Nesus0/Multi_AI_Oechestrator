#!/usr/bin/env python3
"""nesus_ai: tiny dependency-free multi-provider API router."""
from __future__ import annotations
import argparse, json, os, sys, time, tomllib, urllib.error, urllib.request
from pathlib import Path
from typing import Any

APP='nesus-ai'; VERSION='1.0.0'
CONFIG_DIR=Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/APP
CONFIG_PATH=CONFIG_DIR/'config.toml'; SECRETS_PATH=CONFIG_DIR/'secrets.env'; INSTRUCTIONS_PATH=CONFIG_DIR/'instructions.md'
DEFAULT_INSTRUCTIONS='''# nesus_ai Global Instructions\n\nYou are a lightweight orchestration agent.\n\n- Complete the user request with the fewest API calls possible.\n- Prefer correctness, small context, targeted edits, and reversible changes.\n- Never invent results or claim tests passed when they were not run.\n- If a provider fails, switch provider and continue within configured limits.\n- Never expose secrets.\n- Stop when the task is complete and return a compact result.\n'''
DEFAULT_CONFIG='''[general]\nprovider_order = ["cerebras", "groq", "openrouter"]\ntimeout_seconds = 90\nmax_attempts = 6\nmax_prompt_chars = 24000\n\n[providers.cerebras]\nenabled = true\nprotocol = "openai"\nbase_url = "https://api.cerebras.ai/v1"\nmodel = "gpt-oss-120b"\nauth = "bearer"\nkey_env = "CEREBRAS_API_KEY"\n\n[providers.groq]\nenabled = true\nprotocol = "openai"\nbase_url = "https://api.groq.com/openai/v1"\nmodel = "llama-3.3-70b-versatile"\nauth = "bearer"\nkey_env = "GROQ_API_KEY"\n\n[providers.openrouter]\nenabled = true\nprotocol = "openai"\nbase_url = "https://openrouter.ai/api/v1"\nmodel = "openrouter/free"\nauth = "bearer"\nkey_env = "OPENROUTER_API_KEY"\nheaders = { X-OpenRouter-Title = "nesus_ai" }\n'''
DEFAULT_SECRETS='''# chmod 600 ~/.config/nesus-ai/secrets.env\nCEREBRAS_API_KEY=\nGROQ_API_KEY=\nOPENROUTER_API_KEY=\n'''

def load_env(path: Path)->dict[str,str]:
    out={}
    if not path.exists(): return out
    for raw in path.read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1); v=v.strip()
        if len(v)>1 and v[0]==v[-1] and v[0] in "'\"": v=v[1:-1]
        out[k.strip()]=v
    return out

def load_config()->dict[str,Any]:
    if not CONFIG_PATH.exists(): raise FileNotFoundError(f'Run: {APP} init')
    with CONFIG_PATH.open('rb') as f: return tomllib.load(f)

def write_file(path:Path, content:str, mode:int=0o600, force:bool=False)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and not force: return
    path.write_text(content,encoding='utf-8'); os.chmod(path,mode)

def q(label:str, default:str='')->str:
    suffix=f' [{default}]' if default else ''
    value=input(f'{label}{suffix}: ').strip(); return value or default

def append_provider(name:str, protocol:str, base_url:str, model:str, auth:str, key_env:str, header_name:str='')->None:
    safe=''.join(c if c.isalnum() or c in '_-' else '_' for c in name.lower()).strip('_')
    if not safe: raise ValueError('Invalid provider name')
    lines=[f'\n[providers.{safe}]','enabled = true',f'protocol = {json.dumps(protocol)}',f'base_url = {json.dumps(base_url.rstrip("/"))}',f'model = {json.dumps(model)}',f'auth = {json.dumps(auth)}',f'key_env = {json.dumps(key_env)}']
    if header_name: lines.append(f'auth_header = {json.dumps(header_name)}')
    with CONFIG_PATH.open('a',encoding='utf-8') as f: f.write('\n'.join(lines)+'\n')
    env=load_env(SECRETS_PATH)
    if key_env not in env:
        with SECRETS_PATH.open('a',encoding='utf-8') as f: f.write(f'{key_env}=\n')
    print(f'Added provider: {safe}')

def add_provider_interactive()->None:
    print('Type: 1) Google Gemini  2) OpenAI-compatible/proxy  3) Claude-compatible/proxy')
    kind=q('Choice','2')
    if kind=='1':
        append_provider('google','openai','https://generativelanguage.googleapis.com/v1beta/openai','gemini-3.6-flash','bearer','GEMINI_API_KEY'); return
    name=q('Provider name','custom'); base=q('Base URL'); model=q('Model')
    protocol='anthropic' if kind=='3' else 'openai'
    mode=q('Authentication: bearer/header/none','bearer').lower(); header=''
    if mode=='header': header=q('Header name','x-api-key')
    key_env=q('Environment variable', ''.join(c if c.isalnum() else '_' for c in name.upper())+'_API_KEY')
    append_provider(name,protocol,base,model,mode,key_env,header)

def init(force:bool=False)->int:
    write_file(CONFIG_PATH,DEFAULT_CONFIG,force=force); write_file(SECRETS_PATH,DEFAULT_SECRETS,force=force); write_file(INSTRUCTIONS_PATH,DEFAULT_INSTRUCTIONS,force=force)
    print(f'Configuration: {CONFIG_PATH}\nSecrets: {SECRETS_PATH}\nInstructions: {INSTRUCTIONS_PATH}')
    if sys.stdin.isatty() and q('Add Google or another provider now? y/N','n').lower() in {'y','yes','o','oui'}: add_provider_interactive()
    return 0

def headers_for(p:dict[str,Any], key:str)->dict[str,str]:
    h={'Content-Type':'application/json','User-Agent':f'nesus-ai/{VERSION}'}; h.update({str(k):str(v) for k,v in p.get('headers',{}).items()})
    auth=p.get('auth','bearer')
    if auth=='bearer' and key: h['Authorization']=f'Bearer {key}'
    elif auth=='header' and key: h[str(p.get('auth_header','x-api-key'))]=key
    return h

def request_provider(name:str,p:dict[str,Any],prompt:str,timeout:int,secrets:dict[str,str])->str:
    env_name=str(p.get('key_env','')); key=secrets.get(env_name,'')
    if p.get('auth','bearer')!='none' and not key: raise RuntimeError('missing API key')
    protocol=p.get('protocol','openai'); base=str(p['base_url']).rstrip('/'); model=str(p['model'])
    if protocol=='anthropic':
        url=base if base.endswith('/v1/messages') else base+'/v1/messages'; body={'model':model,'max_tokens':4096,'messages':[{'role':'user','content':prompt}]}; h=headers_for(p,key); h.setdefault('anthropic-version','2023-06-01')
    else:
        url=base if base.endswith('/chat/completions') else base+'/chat/completions'; body={'model':model,'messages':[{'role':'system','content':'Follow the supplied global instructions.'},{'role':'user','content':prompt}],'stream':False}; h=headers_for(p,key)
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers=h,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: data=json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail=e.read(1200).decode(errors='replace'); raise RuntimeError(f'HTTP {e.code}: {detail}') from e
    if protocol=='anthropic': return ''.join(str(x.get('text','')) for x in data.get('content',[]) if isinstance(x,dict))
    return str(data['choices'][0]['message']['content'])

def build_prompt(task:str,max_chars:int)->str:
    ins=INSTRUCTIONS_PATH.read_text(encoding='utf-8') if INSTRUCTIONS_PATH.exists() else DEFAULT_INSTRUCTIONS
    text=f'{ins.strip()}\n\n# User task\n{task.strip()}'
    return text if len(text)<=max_chars else text[:max_chars]+'\n[context truncated]'

def run_task(task:str,provider:str|None=None)->int:
    cfg=load_config(); g=cfg.get('general',{}); providers=cfg.get('providers',{}); secrets={**load_env(SECRETS_PATH),**os.environ}
    order=[provider] if provider else list(g.get('provider_order',providers.keys())); errors=[]; prompt=build_prompt(task,int(g.get('max_prompt_chars',24000)))
    for attempts,name in enumerate(order,1):
        p=providers.get(name)
        if not isinstance(p,dict) or not p.get('enabled',True): continue
        try:
            print(f'[{name}]',file=sys.stderr); print(request_provider(name,p,prompt,int(g.get('timeout_seconds',90)),secrets)); return 0
        except Exception as exc:
            errors.append(f'{name}: {exc}'); print(errors[-1],file=sys.stderr)
            if attempts>=int(g.get('max_attempts',6)): break
            time.sleep(min(2,0.25*attempts))
    print('All providers failed:\n- '+'\n- '.join(errors),file=sys.stderr); return 1

def doctor(probe:bool=False)->int:
    cfg=load_config(); secrets={**load_env(SECRETS_PATH),**os.environ}; bad=0
    print(f'nesus_ai {VERSION}\nconfig={CONFIG_PATH}\ninstructions={INSTRUCTIONS_PATH}')
    for name,p in cfg.get('providers',{}).items():
        status='configured' if secrets.get(str(p.get('key_env',''))) or p.get('auth')=='none' else 'missing-key'
        print(f'{name}: {status} model={p.get("model")} url={p.get("base_url")}'); bad += status=='missing-key'
    if probe: print('Probe uses a real request: nesus_ai run --provider NAME "Reply OK"')
    return 1 if bad else 0

def main()->int:
    ap=argparse.ArgumentParser(prog='nesus_ai'); ap.add_argument('--version',action='version',version=VERSION); sp=ap.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('init'); p.add_argument('--force',action='store_true'); sp.add_parser('add-provider'); d=sp.add_parser('doctor'); d.add_argument('--probe',action='store_true'); r=sp.add_parser('run'); r.add_argument('task',nargs='?'); r.add_argument('--provider')
    args=ap.parse_args()
    if args.cmd=='init': return init(args.force)
    if args.cmd=='add-provider': return add_provider_interactive() or 0
    if args.cmd=='doctor': return doctor(args.probe)
    task=args.task or sys.stdin.read()
    if not task.strip(): print('Task required',file=sys.stderr); return 2
    return run_task(task,args.provider)
if __name__=='__main__':
    try: raise SystemExit(main())
    except KeyboardInterrupt: raise SystemExit(130)
