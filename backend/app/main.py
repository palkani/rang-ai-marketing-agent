import os, sqlite3, json, datetime, logging, textwrap
from pathlib import Path
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageOps
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import requests

ROOT=Path("/app")
DATA=ROOT/"data"
OUT=ROOT/"assets/output"
PHOTOS=ROOT/"assets/photos"
for folder in (DATA, OUT, PHOTOS):
    folder.mkdir(parents=True, exist_ok=True)
DB=DATA/"rang.db"
TZ=ZoneInfo("America/New_York")
scheduler=BackgroundScheduler(timezone=TZ)
logging.basicConfig(level=logging.INFO)

def conn():
    c=sqlite3.connect(DB, timeout=15)
    c.row_factory=sqlite3.Row
    return c

def init():
    with conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS campaigns (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, heading TEXT NOT NULL, dishes TEXT NOT NULL, hours TEXT NOT NULL, happy INTEGER NOT NULL, status TEXT NOT NULL, caption TEXT NOT NULL, instagram_id TEXT, facebook_id TEXT, error TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

def setting(key, default=""):
    with conn() as c:
        row=c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

class CampaignIn(BaseModel):
    heading:str="TODAY'S SPECIALS"
    dishes:list[str]=Field(min_length=1,max_length=8)
    hours:str="5 PM – 12 AM"
    happy:bool=True

class SettingsIn(BaseModel):
    draft_time:str=Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

def caption_for(x):
    dishes="\n".join("🍽️ "+d for d in x.dishes)
    happy="\nHappy Hour 5–9 PM | $4 Draft Beer | $5 Premium Pours\n" if x.happy else ""
    return f"{x.heading} at RANG Sip & Dine!\n\n{dishes}\n{happy}\nOpen {x.hours}\n3590 Old Atlanta Rd, Suwanee, GA\n678-456-8710\n\n#RANGSipAndDine #SuwaneeEats #IndianFood #AtlantaFoodies #SuwaneeRestaurants"

def font(size, bold=False):
    path="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, size)

def render(campaign):
    width,height=1080,1350
    im=Image.new("RGB",(width,height),"#121314")
    draw=ImageDraw.Draw(im)
    draw.rectangle((20,20,width-20,height-20),outline="#caa65a",width=4)
    draw.text((width//2,88),"RANG",font=font(106,True),fill="#e9c777",anchor="mt")
    draw.text((width//2,204),"SIP & DINE",font=font(36,True),fill="#ffffff",anchor="mt")
    draw.line((140,277,940,277),fill="#caa65a",width=3)
    draw.text((width//2,307),campaign["heading"].upper()[:35],font=font(52,True),fill="#e9c777",anchor="mt")
    dishes=json.loads(campaign["dishes"])
    y=405
    for name in dishes:
        if y>850:
            break
        for line in textwrap.wrap(name,28):
            draw.text((width//2,y),line,font=font(48,True),fill="#ffffff",anchor="mt")
            y+=64
        y+=20
    photo=PHOTOS/"hero.jpg"
    if photo.exists():
        try:
            p=ImageOps.fit(Image.open(photo).convert("RGB"),(850,270))
            im.paste(p,(115,815))
            draw=ImageDraw.Draw(im)
        except Exception:
            logging.exception("Unable to load hero image")
    if campaign["happy"]:
        draw.rounded_rectangle((100,1100,980,1180),radius=15,fill="#4b371b")
        draw.text((width//2,1110),"HAPPY HOUR 5–9 PM",font=font(39,True),fill="#ffffff",anchor="mt")
        draw.text((width//2,1153),"$4 Draft Beer  |  $5 Premium Pours",font=font(26,True),fill="#f5d28a",anchor="mt")
    draw.text((width//2,1200),"OPEN "+campaign["hours"],font=font(35,True),fill="#e9c777",anchor="mt")
    draw.text((width//2,1250),"3590 Old Atlanta Rd, Suwanee, GA",font=font(25),fill="#ffffff",anchor="mt")
    draw.text((width//2,1290),"678-456-8710",font=font(25,True),fill="#ffffff",anchor="mt")
    path=OUT/("campaign-"+str(campaign["id"])+".jpg")
    im.save(path,"JPEG",quality=88,optimize=True)
    return path

def row(id):
    with conn() as c:
        found=c.execute("SELECT * FROM campaigns WHERE id=?",(id,)).fetchone()
    if not found:
        raise HTTPException(404,"Campaign not found")
    return dict(found)

def create(x):
    with conn() as c:
        cur=c.execute("INSERT INTO campaigns (created_at,heading,dishes,hours,happy,status,caption) VALUES (?,?,?,?,?,?,?)",(datetime.datetime.now(TZ).isoformat(),x.heading,json.dumps(x.dishes),x.hours,int(x.happy),"draft",caption_for(x)))
        id=cur.lastrowid
    render(row(id))
    return row(id)

def scheduled_draft():
    today=datetime.datetime.now(TZ).date().isoformat()
    with conn() as c:
        exists=c.execute("SELECT id FROM campaigns WHERE substr(created_at,1,10)=? LIMIT 1",(today,)).fetchone()
    if not exists:
        create(CampaignIn(dishes=["Add today's specials"],happy=False))
        logging.info("Daily placeholder draft created; manual approval required")

def configure_scheduler():
    hh,mm=map(int,setting("draft_time","14:00").split(":"))
    scheduler.add_job(scheduled_draft,CronTrigger(hour=hh,minute=mm,timezone=TZ),id="daily_draft",replace_existing=True)

@asynccontextmanager
async def lifespan(app):
    init()
    configure_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app=FastAPI(title="RANG Marketing Agent",lifespan=lifespan)

@app.get("/api/health")
def health():
    return {"ok":True,"timezone":"America/New_York"}

@app.get("/api/campaigns")
def campaigns():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT 100")]

@app.post("/api/campaigns")
def new_campaign(x:CampaignIn):
    return create(x)

@app.get("/api/campaigns/{id}")
def get_campaign(id:int):
    return row(id)

@app.put("/api/campaigns/{id}")
def edit_campaign(id:int,x:CampaignIn):
    existing=row(id)
    if existing["status"] not in ("draft","approved","failed"):
        raise HTTPException(409,"Published campaign cannot be edited")
    with conn() as c:
        c.execute('UPDATE campaigns SET heading=?,dishes=?,hours=?,happy=?,caption=?,status="draft",error=NULL WHERE id=?',(x.heading,json.dumps(x.dishes),x.hours,int(x.happy),caption_for(x),id))
    render(row(id))
    return row(id)

@app.post("/api/campaigns/{id}/approve")
def approve(id:int):
    existing=row(id)
    if existing["status"] not in ("draft","failed"):
        raise HTTPException(409,"Only drafts or failed campaigns can be approved")
    with conn() as c:
        c.execute('UPDATE campaigns SET status="approved",error=NULL WHERE id=?',(id,))
    return row(id)

@app.get("/api/campaigns/{id}/image")
def flyer(id:int):
    campaign=row(id)
    path=OUT/("campaign-"+str(id)+".jpg")
    if not path.exists():
        render(campaign)
    return FileResponse(path,media_type="image/jpeg")

@app.get("/api/settings")
def get_settings():
    return {"draft_time":setting("draft_time","14:00"),"public_media_base_url":bool(os.getenv("PUBLIC_MEDIA_BASE_URL")),"meta_configured":bool(os.getenv("META_PAGE_ID") and os.getenv("META_PAGE_ACCESS_TOKEN"))}

@app.put("/api/settings")
def put_settings(x:SettingsIn):
    with conn() as c:
        c.execute("INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",("draft_time",x.draft_time))
    configure_scheduler()
    return get_settings()

def meta_post(url,payload):
    response=requests.post(url,data=payload,timeout=40)
    try:
        data=response.json()
    except Exception:
        raise RuntimeError("Meta HTTP "+str(response.status_code))
    if not response.ok:
        raise RuntimeError(str(data.get("error",data)))
    return data

@app.post("/api/campaigns/{id}/publish")
def publish(id:int):
    campaign=row(id)
    if campaign["status"] not in ("approved","partial","failed"):
        raise HTTPException(409,"Approve the campaign first")
    base=os.getenv("PUBLIC_MEDIA_BASE_URL","").rstrip("/")
    page=os.getenv("META_PAGE_ID","")
    token=os.getenv("META_PAGE_ACCESS_TOKEN","")
    ig=os.getenv("META_IG_USER_ID","")
    version=os.getenv("META_API_VERSION","v23.0")
    if not (base and page and token):
        raise HTTPException(400,"Configure PUBLIC_MEDIA_BASE_URL, META_PAGE_ID, and META_PAGE_ACCESS_TOKEN")
    if not base.startswith("https://"):
        raise HTTPException(400,"Public media URL must use HTTPS")
    image_url=base+"/campaign-"+str(id)+".jpg"
    api="https://graph.facebook.com/"+version
    fb_id=campaign["facebook_id"]
    ig_id=campaign["instagram_id"]
    errors=[]
    if not fb_id:
        try:
            result=meta_post(api+"/"+page+"/photos",{"url":image_url,"caption":campaign["caption"],"access_token":token})
            fb_id=result.get("post_id") or result.get("id")
            with conn() as c:
                c.execute("UPDATE campaigns SET facebook_id=? WHERE id=?",(fb_id,id))
        except Exception as e:
            errors.append("Facebook: "+str(e))
    if ig and not ig_id:
        try:
            container=meta_post(api+"/"+ig+"/media",{"image_url":image_url,"caption":campaign["caption"],"access_token":token})["id"]
            result=meta_post(api+"/"+ig+"/media_publish",{"creation_id":container,"access_token":token})
            ig_id=result["id"]
            with conn() as c:
                c.execute("UPDATE campaigns SET instagram_id=? WHERE id=?",(ig_id,id))
        except Exception as e:
            errors.append("Instagram: "+str(e))
    status="partial" if errors and (fb_id or ig_id) else "failed" if errors else "published"
    with conn() as c:
        c.execute("UPDATE campaigns SET status=?,error=? WHERE id=?",(status,"; ".join(errors) if errors else None,id))
    return row(id)
