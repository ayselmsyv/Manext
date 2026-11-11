import base64, json, os, sqlite3, uuid, urllib.request, urllib.error, hashlib, math
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
UPLOADS = DATA / 'uploads'
UPLOADS.mkdir(parents=True, exist_ok=True)
DB = DATA / 'accesspath.db'
ALLOWED = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}
CATEGORIES = {'Blocked ramp','Missing curb ramp','Damaged sidewalk','Stairs / inaccessible entrance','Obstructed pathway','Other'}
app = FastAPI(title='AccessPath MVP API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
app.mount('/uploads', StaticFiles(directory=str(UPLOADS)), name='uploads')

def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

with connect() as db:
    db.execute('''CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, title TEXT, description TEXT, category TEXT, lat REAL, lng REAL, image_url TEXT, status TEXT, ai_confidence REAL, ai_explanation TEXT, severity TEXT, confirmations INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, created_at TEXT)''')

# Safe, repeatable schema upgrade for the original MVP database.
with connect() as db:
    cols={r['name'] for r in db.execute('PRAGMA table_info(reports)')}
    for name,kind in [('place_type','TEXT'),('demo','INTEGER DEFAULT 0'),('resolved_image_url','TEXT'),('ocr_text','TEXT'),('resolution_status',"TEXT DEFAULT 'open'"),('image_sha256','TEXT')]:
        if name not in cols: db.execute(f'ALTER TABLE reports ADD COLUMN {name} {kind}')

PLACE_TYPES={'Hospital / clinic','School / university','Public transport','Government service','Residential / other'}
def priority_score(severity, place_type, confirmations):
    base={'High':55,'Medium':35,'Low':15,'Unknown':10}.get(severity,10)
    critical={'Hospital / clinic':25,'School / university':18,'Public transport':20,'Government service':16,'Residential / other':5}.get(place_type,5)
    return min(100,base+critical+min(int(confirmations),5)*4)

DEMO_SEEDS=[
 ('demo-hospital','Clinic entrance ramp blocked','A vehicle is blocking the only marked ramp at this sample clinic entrance.','Blocked ramp',40.3790,49.8491,'Hospital / clinic','High',4),
 ('demo-campus','University entrance has steps','Entrance shown with stairs and no accessible alternative confirmed.','Stairs / inaccessible entrance',40.3731,49.8408,'School / university','High',2),
 ('demo-stop','Missing curb cut at bus stop','Raised curb may prevent step-free access to this bus stop.','Missing curb ramp',40.3831,49.8582,'Public transport','Medium',3),
 ('demo-walk','Uneven pavement near crossing','Uneven sidewalk surface; passage may still be possible.','Damaged sidewalk',40.3678,49.8324,'Residential / other','Low',1),
]
with connect() as db:
    for rid,title,description,category,lat,lng,place_type,severity,confirmations in DEMO_SEEDS:
        if db.execute('SELECT 1 FROM reports WHERE id=?',(rid,)).fetchone(): continue
        db.execute('''INSERT INTO reports (id,title,description,category,lat,lng,image_url,status,ai_confidence,ai_explanation,severity,confirmations,xp,created_at,place_type,demo,resolution_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (rid,title,description,category,lat,lng,None,'demo_sample',None,'Illustrative scenario only. Not an actual verified report.',severity,confirmations,0,'2026-11-11T00:00:00+00:00',place_type,1,'open'))

def analyze_photo(image_bytes, mime):
    """Preliminary visual evidence assessment; never authenticates location or date."""
    fallback={'status':'pending_review','confidence':None,'severity':'Unknown','explanation':'AI service is not configured. Report saved; analysis pending.','ocr_text':None,'xp':0,'category':'Other','title':'Accessibility photo awaiting review','description':'Photo uploaded. AI analysis is pending.'}
    key=os.getenv('OPENAI_API_KEY')
    if not key: return fallback
    prompt = """You are reviewing a single user photo for an accessibility reporting app. Evaluate what is VISIBLE, not whether the location or date is genuine.

IMPORTANT: Stairs at a pedestrian/building entrance with a wheelchair user facing them, with no ramp or lift visible IN THE PHOTO, ARE a likely accessibility barrier. Classify as 'Stairs / inaccessible entrance' and barrier_visible=true, even though an alternative accessible entrance might exist outside the frame. Do NOT require a blocked ramp or proof that no other entrance exists. A wheelchair user alone, without a visible physical obstacle, is NOT enough.

Other visible examples: vehicle blocking a ramp; high curb without visible curb cut; broken/impassable sidewalk; objects obstructing a pedestrian route. Normal accessible paths with no obstacle are NOT barriers. Blurry or ambiguous images should be marked uncertain.

Respond with one JSON object with keys: barrier_visible (true/false), decision ('barrier'|'no_barrier'|'uncertain'), category (exactly one of 'Blocked ramp','Missing curb ramp','Damaged sidewalk','Stairs / inaccessible entrance','Obstructed pathway','Other'), title (brief), description (one factual sentence limited to visible content), severity ('Low'|'Medium'|'High'|'Unknown'), explanation (brief visual reasoning, mention uncertainty about alternatives), ocr_text (only clearly readable text, otherwise empty). Never invent an address, date, sign, or absent alternative route."""
    body={'model':os.getenv('OPENAI_MODEL','gpt-4o-mini'),'temperature':0,'response_format':{'type':'json_object'},'messages':[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':f'data:{mime};base64,{base64.b64encode(image_bytes).decode()}','detail':'high'}}]}]}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=40) as response: raw=json.load(response)
        parsed=json.loads(raw['choices'][0]['message']['content'])
        decision=parsed.get('decision')
        matched=parsed.get('barrier_visible') is True and decision=='barrier'
        if decision not in ('barrier','no_barrier','uncertain'):
            matched=parsed.get('barrier_visible') is True
            decision='barrier' if matched else 'uncertain'
        category=parsed.get('category') if parsed.get('category') in CATEGORIES else 'Other'
        severity=parsed.get('severity') if parsed.get('severity') in ('Low','Medium','High') else 'Unknown'
        state='ai_reviewed' if matched else ('not_eligible' if decision=='no_barrier' else 'needs_review')
        return {'status':state,'confidence':None,'severity':severity,'explanation':str(parsed.get('explanation') or '')[:350],'ocr_text':str(parsed.get('ocr_text') or '')[:500],'xp':10 if matched else 0,'category':category,'title':str(parsed.get('title') or 'Accessibility observation')[:120],'description':str(parsed.get('description') or 'Image submitted for accessibility review.')[:1200]}
    except urllib.error.HTTPError as e:
        print(f'AccessPath AI API HTTP error: {e.code}', flush=True)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
        print(f'AccessPath AI analysis unavailable: {type(e).__name__}', flush=True)
    return {**fallback,'status':'analysis_unavailable','explanation':'AI analysis could not be completed. Check backend terminal and API configuration. No XP awarded.'}

@app.get('/api/health')
def health():
    return {'ok':True,'ai_configured':bool(os.getenv('OPENAI_API_KEY'))}

@app.get('/api/reports')
def reports():
    with connect() as db:
        return [dict(x,priority=priority_score(x['severity'],x['place_type'],x['confirmations'])) for x in db.execute('SELECT * FROM reports ORDER BY demo DESC, created_at DESC')]

@app.post('/api/reports')
async def create_report(image: UploadFile = File(...), lat: float = Form(...), lng: float = Form(...), place_type: str = Form('Residential / other')):
    if place_type not in PLACE_TYPES: raise HTTPException(400,'Invalid place type')
    if not (-90<=lat<=90 and -180<=lng<=180): raise HTTPException(400,'Invalid coordinates')
    if image.content_type not in ALLOWED: raise HTTPException(400,'Only JPG, PNG, WEBP supported')
    contents=await image.read(5*1024*1024+1)
    if len(contents)>5*1024*1024: raise HTTPException(413,'Max image size 5MB')
    if not contents: raise HTTPException(400,'Empty image')
    # Basic file signatures prevent obvious MIME spoofing.
    signatures={'image/jpeg':contents.startswith(b'\xff\xd8\xff'),'image/png':contents.startswith(b'\x89PNG\r\n\x1a\n'),'image/webp':contents[:4]==b'RIFF' and contents[8:12]==b'WEBP'}
    if not signatures[image.content_type]: raise HTTPException(400,'Image format does not match file')
    digest=hashlib.sha256(contents).hexdigest()
    rid=uuid.uuid4().hex[:12]
    filename=rid+ALLOWED[image.content_type]
    (UPLOADS/filename).write_bytes(contents)
    analysis=analyze_photo(contents,image.content_type)
    # Award only for an AI-visible barrier, and never for an identical image.
    # Nearby same-category reports are conservatively queued for review to reduce XP farming.
    if analysis['xp']:
        with connect() as db:
            same_image=db.execute('SELECT id FROM reports WHERE image_sha256=? AND demo=0 LIMIT 1',(digest,)).fetchone()
            nearby=db.execute('SELECT id,lat,lng FROM reports WHERE category=? AND demo=0 AND status=?',(analysis['category'],'ai_reviewed')).fetchall()
        latrad=math.radians(lat)
        nearby_match=any(2*6371000*math.asin(min(1,math.sqrt(math.sin(math.radians(lat-r['lat'])/2)**2+math.cos(latrad)*math.cos(math.radians(r['lat']))*math.sin(math.radians(lng-r['lng'])/2)**2)))<25 for r in nearby)
        if same_image or nearby_match:
            analysis['xp']=0
            analysis['status']='duplicate_review'
            analysis['explanation']='Possible duplicate report. No XP until independent review.'
    row={'image_sha256':digest,'id':rid,'title':analysis['title'],'description':analysis['description'],'category':analysis['category'],'lat':lat,'lng':lng,'image_url':'/uploads/'+filename,'status':analysis['status'],'ai_confidence':analysis['confidence'],'ai_explanation':analysis['explanation'],'ocr_text':analysis['ocr_text'],'severity':analysis['severity'],'confirmations':0,'xp':analysis['xp'],'created_at':datetime.now(timezone.utc).isoformat(),'place_type':place_type,'demo':0,'resolved_image_url':None,'resolution_status':'open'}
    with connect() as db:
        db.execute('''INSERT INTO reports (id,title,description,category,lat,lng,image_url,status,ai_confidence,ai_explanation,severity,confirmations,xp,created_at,place_type,demo,resolved_image_url,resolution_status,ocr_text,image_sha256) VALUES (:id,:title,:description,:category,:lat,:lng,:image_url,:status,:ai_confidence,:ai_explanation,:severity,:confirmations,:xp,:created_at,:place_type,:demo,:resolved_image_url,:resolution_status,:ocr_text,:image_sha256)''',row)
    return dict(row,priority=priority_score(row['severity'],row['place_type'],0))

@app.post('/api/reports/{rid}/confirm')
def confirm(rid: str):
    # Demo-only action: no authentication, rate limiting, or independent-user verification.
    with connect() as db:
        row=db.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone()
        if not row: raise HTTPException(404,'Report not found')
        db.execute('UPDATE reports SET confirmations=confirmations+1 WHERE id=?',(rid,))
        result=dict(db.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone())
        return dict(result,priority=priority_score(result['severity'],result['place_type'],result['confirmations']))


@app.post('/api/reports/{rid}/resolution-photo')
async def resolution_photo(rid: str, image: UploadFile=File(...)):
    # This is evidence submission, NOT automatic confirmation of a repair.
    with connect() as db:
        report=db.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone()
        if not report: raise HTTPException(404,'Report not found')
    if image.content_type not in ALLOWED: raise HTTPException(400,'Unsupported image format')
    raw=await image.read(5*1024*1024+1)
    if len(raw)>5*1024*1024 or not raw: raise HTTPException(400,'Image must be 1 byte to 5MB')
    signatures={'image/jpeg':raw.startswith(b'\xff\xd8\xff'),'image/png':raw.startswith(b'\x89PNG\r\n\x1a\n'),'image/webp':raw[:4]==b'RIFF' and raw[8:12]==b'WEBP'}
    if not signatures[image.content_type]: raise HTTPException(400,'Invalid image signature')
    name=uuid.uuid4().hex[:12]+ALLOWED[image.content_type]
    (UPLOADS/name).write_bytes(raw)
    with connect() as db:
        db.execute('UPDATE reports SET resolved_image_url=?, resolution_status=? WHERE id=?',('/uploads/'+name,'needs_independent_review',rid))
    return {'resolution_status':'needs_independent_review','resolved_image_url':'/uploads/'+name,'message':'After photo received. Human review required; repair not confirmed.'}

@app.get('/api/reports/{rid}/action-report')
def action_report(rid: str):
    with connect() as db:
        row=db.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone()
        if not row: raise HTTPException(404,'Report not found')
        r=dict(row)
        return {'demo':bool(r['demo']),'title':r['title'],'category':r['category'],'description':r['description'],'location':{'lat':r['lat'],'lng':r['lng']},'place_type':r['place_type'],'severity':r['severity'],'priority_score':priority_score(r['severity'],r['place_type'],r['confirmations']),'community_confirmations_demo_only':r['confirmations'],'resolution_status':r['resolution_status'],'disclaimer':'Draft for review. Not submitted to any government agency. Demo data is fictional.'}

FRONTEND=ROOT.parent/'frontend'
app.mount('/',StaticFiles(directory=str(FRONTEND),html=True),name='frontend')
