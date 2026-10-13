"""Editable, deterministic 1080p Probaho motion presentation renderer.

No app/database writes and no generated receipts. Financial graphics illustrate
the documented synthetic Shapla fixture; screenshots are genuine captured UI.
Pass the production scenes JSON and a narration track to make the final video.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess
import time
import wave
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 25
HERE = Path(__file__).resolve().parent
PRODUCTION = HERE.parent
APP = PRODUCTION.parents[1]
ASSETS = PRODUCTION / "assets"
INK = "#F7F9FF"
MUTED = "#ADBEDF"
TEAL = "#37D5D7"
AMBER = "#FFB64D"
RED = "#FF8E9F"
BLUE = "#89ADFF"
PANEL = "#14244B"
BORDER = "#304C7C"


def clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def ease(value: float) -> float:
    return 1.0 - (1.0 - clamp(value)) ** 3


def phase(progress: float, delay: float = 0.0, span: float = .14) -> float:
    return ease((progress - delay) / span)


@lru_cache(maxsize=80)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    choices = [Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
               Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")]
    for candidate in choices:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    raise RuntimeError("Install a Unicode TrueType font or update font() paths.")


@lru_cache(maxsize=500)
def glyph(text: str, size: int, color: str, bold: bool = False) -> Image.Image:
    f = font(size, bold)
    box = f.getbbox(text or " ")
    image = Image.new("RGBA", (max(1, box[2] - min(0, box[0]) + 4), size + 17), (0, 0, 0, 0))
    ImageDraw.Draw(image).text((2 - min(0, box[0]), -box[1]), text, font=f, fill=color)
    return image


def text(image: Image.Image, value: str, x: float, y: float, size: int = 36,
         color: str = INK, bold: bool = False, align: str = "left", alpha: float = 1.0) -> None:
    if not value or alpha <= 0:
        return
    item = glyph(str(value), size, color, bold)
    if align == "center":
        x -= item.width / 2
    elif align == "right":
        x -= item.width
    if alpha < .995:
        item = item.copy()
        item.putalpha(item.getchannel("A").point(lambda a: int(a * alpha)))
    image.paste(item, (round(x), round(y)), item)


@lru_cache(maxsize=300)
def wrapped(value: str, size: int, width: int, bold: bool = False) -> tuple[str, ...]:
    lines: list[str] = []
    for paragraph in value.split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = (current + " " + word).strip()
            if font(size, bold).getlength(candidate) <= width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return tuple(lines)


def paragraph(image: Image.Image, value: str, x: int, y: int, size: int = 35,
              width: int = 550, color: str = MUTED, bold: bool = False,
              leading: float = 1.35, alpha: float = 1.0) -> int:
    for line in wrapped(value, size, width, bold):
        text(image, line, x, y, size, color, bold, alpha=alpha)
        y += round(size * leading)
    return y


def panel(image: Image.Image, box: tuple[int, int, int, int], fill: str = PANEL,
          outline: str = BORDER, radius: int = 25, width: int = 2) -> None:
    ImageDraw.Draw(image).rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def rule(image: Image.Image, xy: tuple[int, int, int, int], color: str = BORDER, width: int = 2) -> None:
    ImageDraw.Draw(image).line(xy, fill=color, width=width)


def pill(image: Image.Image, value: str, x: int, y: int, color: str = TEAL,
         size: int = 26, fill: str = "#152C4B") -> None:
    width = round(font(size).getlength(value)) + 38
    panel(image, (x, y, x + width, y + 45), fill, color, 22, 1)
    text(image, value, x + 19, y + 9, size, color)


def money(number: int | float, sign: bool = False) -> str:
    number = int(round(number))
    return ("−" if number < 0 else "+" if sign and number > 0 else "") + f"{abs(number):,}"


def background() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W]
    g1 = np.exp(-(((xx - 1510) / 800) ** 2 + ((yy - 160) / 620) ** 2))
    g2 = np.exp(-(((xx - 280) / 730) ** 2 + ((yy - 770) / 660) ** 2))
    pixels = np.stack([8 + 19*g1 + 1*g2, 15 + 36*g1 + 13*g2, 46 + 66*g1 + 23*g2], axis=2)
    im = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im)
    for x in range(120, W-100, 96):
        for y in range(130, H-65, 96):
            d.ellipse((x,y,x+2,y+2),fill=(31,48,89))
    return im


BACKGROUND = background()


def heading(image: Image.Image, scene: dict[str, Any], subtitle: str = "") -> None:
    panel(image, (118, 48, 172, 102), "#10384B", TEAL, 16, 1)
    text(image, "P", 145, 58, 35, TEAL, True, "center")
    text(image, "Probaho", 188, 58, 34, INK, True)
    text(image, "TOPIC E  ·  SME FINANCE", 405, 65, 23, MUTED)
    pill(image, "Synthetic BDT sandbox", 1439, 53, MUTED, 25, "#172952")
    title = scene.get("title", "Probaho")
    size = 73
    if font(size, True).getlength(title) > 1680:
        size = 64
    text(image, title, 118, 163, size, INK, True)
    if subtitle:
        text(image, subtitle, 121, 265, 31, MUTED)


def footer(image: Image.Image, index: int, count: int, total_progress: float,
           preview: bool = False) -> None:
    text(image, "MOTION PREVIEW" if preview else "PRODUCT PRESENTATION  ·  LOCAL SANDBOX", 120, 991, 23, MUTED)
    text(image, f"{index+1:02d} / {count:02d}", 1800, 991, 24, MUTED, align="right")
    rule(image, (120, 1041, 1800, 1041), "#273D69", 4)
    rule(image, (120, 1041, int(120 + 1680*clamp(total_progress)), 1041), TEAL, 4)


def find_asset(name: str) -> Path | None:
    candidate = ASSETS / name
    if candidate.exists():
        return candidate
    # Old screenshots may include imported changes. Use fresh production assets
    # by default. A caller may explicitly provide an older screenshot path.
    return None


def resolve_path(value: str | Path, base: Path = PRODUCTION) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    for candidate in [base/path, APP/path, Path.cwd()/path]:
        if candidate.exists():
            return candidate
    return base/path


def prepare_screen(scene: dict[str, Any], default: str, width: int, height: int,
                   default_crop: tuple[int,int,int,int] | None = None) -> Image.Image:
    selected = resolve_path(scene["screenshot"]) if scene.get("screenshot") else find_asset(default)
    block = Image.new("RGB", (width, height), "#EDF2F2")
    d = ImageDraw.Draw(block)
    d.rectangle((0,0,width,42),fill="#DAE3E9")
    for j, color in enumerate(["#DF847F", "#D7B866", "#75AE90"]):
        d.ellipse((17+j*25,14,28+j*25,25),fill=color)
    text(block,"Probaho  ·  captured interface",110,10,20,"#41606A")
    if selected and selected.exists():
        source = Image.open(selected).convert("RGB")
        crop = scene.get("crop") or scene.get("focus_crop") or default_crop
        if crop:
            x1,y1,x2,y2 = crop
            source = source.crop((max(0,x1),max(0,y1),min(source.width,x2),min(source.height,y2)))
        scale=min((width-16)/source.width,(height-58)/source.height)
        source=source.resize((max(1,round(source.width*scale)),max(1,round(source.height*scale))),Image.Resampling.LANCZOS)
        block.paste(source,((width-source.width)//2,47+(height-58-source.height)//2))
    else:
        d.rectangle((12,55,width-12,height-12), fill="#E4EBEA")
        text(block,"Fresh interface capture",width/2,height/2-28,34,"#174D48",True,"center")
        text(block,"Awaiting production assets",width/2,height/2+25,24,"#4C746F",align="center")
    mask=Image.new("L",block.size,0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,width-1,height-1),radius=21,fill=255)
    out=block.convert("RGBA");out.putalpha(mask)
    return out


def reveal(image: Image.Image, layer: Image.Image, x: int, y: int,
           amount: float, distance: int = 28) -> None:
    if amount <= 0:
        return
    if amount < .995:
        layer=layer.copy()
        layer.putalpha(layer.getchannel("A").point(lambda a:int(a*amount)))
    image.paste(layer,(x,y+round(distance*(1-amount))),layer)


def push_screen(layer: Image.Image, progress: float) -> Image.Image:
    """A subtle, centered camera push with a stable rounded viewport."""
    # Quantizing to 24 positions reduces expensive resizing without visible
    # stepping: the complete push is only 24 pixels over the narration window.
    zoom=1+round(clamp(progress)*24)/1000
    if zoom<=1:return layer
    w,h=layer.size
    expanded=layer.resize((round(w*zoom),round(h*zoom)),Image.Resampling.BICUBIC)
    x=(expanded.width-w)//2;y=(expanded.height-h)//2
    cropped=expanded.crop((x,y,x+w,y+h))
    cropped.putalpha(layer.getchannel("A"))
    return cropped


def node(image: Image.Image, x: int, y: int, label: str, sub: str, active: float,
         color: str = TEAL, number: str = "") -> None:
    d=ImageDraw.Draw(image)
    d.ellipse((x-34,y-34,x+34,y+34),fill="#122849",outline=color if active>.5 else BORDER,width=3)
    if number:
        text(image,number,x,y-18,31,color if active>.5 else MUTED,True,"center")
    else:
        d.ellipse((x-11,y-11,x+11,y+11),fill=color if active>.5 else BORDER)
    text(image,label,x,y+67,31,INK,True,"center",alpha=max(.25,active))
    if sub:
        text(image,sub,x,y+111,25,MUTED,align="center",alpha=max(.25,active))


class Scene:
    def __init__(self, scene: dict[str, Any], duration: float, kind: str):
        self.data, self.duration, self.kind = scene, duration, kind
        self.base=BACKGROUND.copy()
        self.screens: dict[str,Image.Image]={}
        subtitles={
          "problem":"Payroll, receivables and supplier bills share one calendar.",
          "product":"Approval-gated SME cash-flow recovery",
          "waterfall":"Shapla Services  ·  target: 31 Oct 2026  ·  all values in BDT",
          "records":"A clear business scope, linked inputs and atomic validation",
          "timeline":"Scheduled collections are assumptions until money is received.",
          "comparison":"Compare action effects before choosing a recovery plan.",
          "workflow":"Source bill: bill-supplier-001  ·  Payee: Rahman Supplies",
          "execution":"An approved schedule change, followed by post-commit read-back",
          "security":"The model explains and proposes. Authority stays bounded.",
          "assistant":"The displayed mode is deterministic and labelled Local demo.",
          "verification":"Synthetic correctness and safety checks; measured evidence only",
          "closing":"Records become a cash gap, a reviewed action and an evidence trail.",
          "screenshot":"Captured product interface  ·  synthetic local records",
        }
        heading(self.base,scene,scene.get("subtitle",subtitles.get(kind,"")))
        if kind=="product":
            self.screens["main"]=prepare_screen(scene,"overview.png",1060,570,(275,210,1415,925))
        if kind=="records":
            self.screens["main"]=prepare_screen(scene,"records.png",1140,585,(260,95,1440,745))
            self.screens["import"]=prepare_screen({},"import-preview.png",1140,585,(463,245,979,581))
        if kind=="workflow":
            self.screens["approved"]=prepare_screen({},"approved.png",1140,585,(310,151,1381,454))
            self.screens["consent"]=prepare_screen({},"consent.png",1140,585,(310,475,1380,735))
        if kind=="execution":
            self.screens["receipt"]=prepare_screen({},"executed.png",1140,585,(310,43,930,196))
            self.screens["readback"]=prepare_screen({},"readback.png",1140,585,(1070,129,1375,198))
        if kind=="security":
            self.screens["activity"]=prepare_screen({},"activity.png",1140,585,(372,413,626,669))
        if kind=="assistant":
            self.screens["main"]=prepare_screen(scene,"assistant.png",1130,588,(255,120,1435,755))
        if kind=="screenshot":
            self.screens["main"]=prepare_screen(scene,"overview.png",1520,610)

    def render(self,t: float) -> Image.Image:
        p=clamp(t/self.duration)
        image=self.base.copy()
        method=getattr(self,"draw_"+self.kind,self.draw_closing)
        method(image,p)
        # Gentle fades over the shared radial background avoid harsh cuts.
        alpha=min(clamp(t/.42),clamp((self.duration-t)/.38))
        if alpha<.999:
            image=Image.blend(BACKGROUND,image,alpha)
        return image

    def ui_view(self,im:Image.Image,key:str,p:float,start:float,title:str,
                notes:list[str],color:str=TEAL) -> None:
        """Transition to an actual captured, focused product state.

        The image is kept distinct from authored callouts, so annotations do not
        impersonate app controls or alter captured states.
        """
        amount=phase(p,start,.055)
        if amount<=0:return
        view=self.base.copy()
        local=clamp((p-start)/max(.1,1-start))
        reveal(view,push_screen(self.screens[key],local),120,350,1)
        pill(view,"ACTUAL UI CAPTURE",1300,358,color,25)
        yy=paragraph(view,title,1302,442,46,488,INK,True,1.22)+36
        for j,note in enumerate(notes):
            if not note.strip():continue
            a=phase(local,.03+j*.12,.23)
            if a>.05:rule(view,(1303,yy+7,1319,yy+7),color,4)
            yy=paragraph(view,note,1338,yy-4,31,446,MUTED,False,1.3,a)+36
        text(view,"Isolated synthetic run",690,949,26,MUTED,align="center")
        im.paste(Image.blend(im,view,amount),(0,0))

    def draw_problem(self,im:Image.Image,p:float)->None:
        d=ImageDraw.Draw(im)
        centers=[380,960,1540]
        labels=[("Payroll","80,000 BDT","Due 31 Oct",TEAL),
                ("Receivable","20,000 BDT","Expected 31 Oct",BLUE),
                ("Supplier bill","70,000 BDT","Due 31 Oct",AMBER)]
        for i,(title,amount,date,color) in enumerate(labels):
            a=phase(p,.06+i*.12,.15); y=382+int(38*(1-a)); x=centers[i]-235
            if a<=0:continue
            panel(im,(x,y,x+470,y+327),"#14274E",color)
            pill(im,date,x+29,y+26,color,25)
            text(im,title,x+29,y+110,43,INK,True,alpha=a)
            text(im,amount,x+29,y+183,43,color,True,alpha=a)
            text(im,["Protect the team","Collection can move","Payment still matters"][i],x+29,y+257,27,MUTED,alpha=a)
        a=phase(p,.37,.2)
        rule(im,(380,786,int(380+1160*a),786),TEAL,5)
        for i,x in enumerate(centers):
            if a>i*.45: d.ellipse((x-10,776,x+10,796),fill=TEAL)
        text(im,"When dates collide, cash pressure becomes a decision.",960,861,38,INK,True,"center",phase(p,.5,.13))

    def draw_product(self,im:Image.Image,p:float)->None:
        a=phase(p,.04,.17)
        text(im,"Probaho",119,400,106,INK,True,alpha=a)
        paragraph(im,"See the gap.\nCompare the options.\nApprove the next action.",123,543,42,610,TEAL,True,1.43,a)
        pill(im,"Owner in control",121,805,AMBER,29)
        reveal(im,self.screens["main"],741,351,phase(p,.11,.22),40)
        text(im,"Real interface  ·  synthetic records",1270,941,26,MUTED,align="center",alpha=phase(p,.28,.15))

    def draw_waterfall(self,im:Image.Image,p:float)->None:
        d=ImageDraw.Draw(im)
        y0,y1=364,832
        def yy(v:float)->int:return round(y1-(v+30000)/190000*(y1-y0))
        base=yy(0)
        for value in [0,50000,100000,150000]:
            y=yy(value);rule(im,(170,y,1780,y),"#283F68",1)
            text(im,f"{value//1000}k",122,y-15,22,MUTED)
        # The policy reserve is distinct from cash balance.
        y=yy(20000)
        for x in range(170,1780,25):rule(im,(x,y,x+13,y),AMBER,2)
        pill(im,"Reserve floor 20,000",1400,308,AMBER,24)
        values=[(0,120000,"Opening",TEAL),(120000,140000,"Receivable",TEAL),
                (140000,60000,"Payroll",AMBER),(60000,-10000,"Supplier",AMBER),
                (0,-10000,"Closing",RED)]
        for i,(start,end,label,color) in enumerate(values):
            a=phase(p,.07+i*.095,.15); x=190+i*323; w=220
            if a<=0:continue
            current=start+(end-start)*a
            top=min(yy(start),yy(current)); bottom=max(yy(start),yy(current))
            d.rounded_rectangle((x,top,x+w,max(top+3,bottom)),radius=11,fill=color)
            value=end if i==4 else end-start
            label_value=round(value*a) if a<.999 else value
            value_y=bottom+20 if i==4 else max(330,top-63)
            text(im,money(label_value,i in [1,2,3]),x+w/2,value_y,42,color,True,"center")
            text(im,label,x+w/2,875,29,INK,True,"center")
            if i in [1,2,3]:
                prev=values[i-1][1]
                rule(im,(x-100,yy(prev),x,yy(prev)),"#7797C7",2)
        a=phase(p,.58,.14)
        panel(im,(560,932,1360,983),"#382944",RED,22,1)
        text(im,"Closing −10,000  ·  Reserve gap 30,000 BDT",960,943,30,INK,True,"center",a)

    def draw_records(self,im:Image.Image,p:float)->None:
        reveal(im,push_screen(self.screens["main"],p),120,351,phase(p,.05,.2))
        labels=[("01","One business","A selected, isolated scope."),
                ("02","Three record types","Transactions, invoices, bills."),
                ("03","Validate, then write","Whole-file checks are atomic.")]
        for i,(number,title,body) in enumerate(labels):
            a=phase(p,.16+i*.13,.16);y=367+i*190+int(27*(1-a))
            if a<=0:continue
            panel(im,(1300,y,1800,y+154),"#14264D",TEAL if i==2 else BORDER)
            text(im,number,1323,y+25,26,TEAL,True,alpha=a)
            text(im,title,1376,y+24,35,INK,True,alpha=a)
            paragraph(im,body,1376,y+83,28,390,MUTED,alpha=a)
        self.ui_view(im,"import",p,.53,"Validate before writing",
                     ["One CSV: transactions, invoices, bills.",
                      "Local preview checks the selected file.",
                      "The server checks all rows before any write."])

    def draw_timeline(self,im:Image.Image,p:float)->None:
        panel(im,(120,350,1800,629),"#12244A",BORDER)
        text(im,"Invoice collection date",157,385,31,MUTED)
        x1,x2,y=515,1450,515
        rule(im,(x1,y,x2,y),"#476394",6)
        datep=phase(p,.12,.42);x=int(x1+(x2-x1)*datep)
        d=ImageDraw.Draw(im)
        d.ellipse((x-21,y-21,x+21,y+21),fill=AMBER,outline=INK,width=2)
        text(im,"31 Oct",x1,y+55,35,INK,True,"center")
        text(im,"7 Nov",x2,y+55,35,AMBER,True,"center")
        pill(im,"Target date",x1-77,y-101,TEAL,24)
        text(im,"+7 days",1040,404,42,AMBER,True,"center",phase(p,.23,.14))
        for i,(x,title,cash,gap,color) in enumerate([(120,"Scheduled",-10000,30000,BLUE),(990,"Late collection",-30000,50000,AMBER)]):
            a=phase(p,.34+i*.14,.15)
            if a<=0:continue
            yy=684+int(28*(1-a));panel(im,(x,yy,x+810,yy+258),"#14254C",color)
            text(im,title,x+35,yy+25,36,INK,True,alpha=a)
            text(im,"Closing cash",x+35,yy+90,28,MUTED,alpha=a)
            text(im,money(round(cash*a))+" BDT",x+35,yy+135,48,RED,True,alpha=a)
            text(im,"Reserve gap",x+445,yy+90,28,MUTED,alpha=a)
            text(im,money(round(gap*a))+" BDT",x+445,yy+139,44,color,True,alpha=a)

    def draw_comparison(self,im:Image.Image,p:float)->None:
        cards=[("Collection reminder","DRAFT ONLY","0 BDT","No collected cash is recognized.","Draft a reminder",BLUE),
               ("Supplier reschedule","CONSENT REQUIRED","40,000 BDT","Defer to 7 Nov. Keep payroll protected.","Review an action",TEAL),
               ("Mock financing","COMPARISON ONLY","Illustrative terms","Fees and repayment are shown. Execution is disabled.","No lender connected",AMBER)]
        for i,(title,tag,value,body,end,color) in enumerate(cards):
            a=phase(p,.06+i*.15,.18);x=120+i*574;y=367+int(42*(1-a))
            if a<=0:continue
            panel(im,(x,y,x+532,y+528),"#14274E",color,27,2)
            pill(im,tag,x+29,y+30,color,23)
            paragraph(im,title,x+29,y+133,40,474,INK,True,1.25,a)
            text(im,value,x+29,y+268,43 if i<2 else 35,color,True,alpha=a)
            paragraph(im,body,x+29,y+347,30,459,MUTED,False,1.3,a)
            rule(im,(x+29,y+451,x+503,y+451),BORDER,1)
            text(im,end,x+29,y+475,27,color,True,alpha=a)
        text(im,"A reminder is never treated as a collection.",960,939,30,INK,align="center",alpha=phase(p,.56,.14))

    def draw_workflow(self,im:Image.Image,p:float)->None:
        panel(im,(120,350,1000,937),"#14274E",BORDER)
        pill(im,"REVIEW THE EXACT ACTION",151,378,TEAL,24)
        facts=[("Payee","Rahman Supplies"),("Amount","40,000 BDT"),("Source","bill-supplier-001"),
               ("Original date","31 Oct 2026"),("Deferred date","7 Nov 2026")]
        for i,(label,value) in enumerate(facts):
            a=phase(p,.05+i*.055,.14);y=469+i*85
            text(im,label,153,y,29,MUTED,alpha=a)
            text(im,value,962,y-3,36,TEAL if i==1 else INK,True,"right",a)
            if i<4:rule(im,(151,y+52,968,y+52),BORDER,1)
        gates=[("1","Human approval","A separate owner action",TEAL),
               ("2","Supplier acceptance","Explicit sandbox simulation",AMBER),
               ("3","Execute in sandbox","Only after both gates",BLUE)]
        for i,(number,title,body,color) in enumerate(gates):
            a=phase(p,.12+i*.17,.18);x=1060;y=365+i*199+int(26*(1-a))
            if a<=0:continue
            panel(im,(x,y,1800,y+162),"#14274E",color)
            node(im,x+62,y+78,"","",a,color,number)
            text(im,title,x+126,y+37,39,INK,True,alpha=a)
            text(im,body,x+126,y+99,28,MUTED,alpha=a)
        text(im,"The acceptance button represents a simulation, not a real reply.",1430,941,25,MUTED,align="center",alpha=phase(p,.63,.14))
        self.ui_view(im,"approved",p,.44,"The human approval is recorded",
                     ["Payee, bill, amount and dates stay visible.",
                      "Supplier acceptance is a separate gate.",
                      "The model cannot approve this action."])
        self.ui_view(im,"consent",p,.71,"Supplier consent is simulated",
                     ["Actual accepted sandbox state.",
                      "No supplier was contacted.",
                      "Both gates precede execution."],AMBER)

    def draw_execution(self,im:Image.Image,p:float)->None:
        values=[("Before",-10000,30000,RED), ("After approved recovery",30000,0,TEAL)]
        for i,(title,cash,gap,color) in enumerate(values):
            a=phase(p,.06+i*.18,.2);x=120+i*870;y=351+int(28*(1-a))
            if a<=0:continue
            panel(im,(x,y,x+810,y+293),"#14264D",color)
            text(im,title,x+36,y+27,35,INK,True,alpha=a)
            text(im,"Target closing",x+36,y+101,29,MUTED,alpha=a)
            text(im,money(round(cash*a))+" BDT",x+36,y+149,52,color,True,alpha=a)
            text(im,"Reserve gap",x+470,y+104,28,MUTED,alpha=a)
            text(im,money(round(gap*a))+" BDT",x+470,y+158,42,color,True,alpha=a)
        a=phase(p,.34,.14)
        panel(im,(120,687,1800,781),"#382F43",AMBER,22,1)
        text(im,"40,000 BDT remains owed on 7 Nov — the obligation still exists.",960,716,37,AMBER,True,"center",a)
        labels=["Approve","Accept","Execute","Read receipt"]
        for i,label in enumerate(labels):
            x=320+i*435;a=phase(p,.24+i*.1,.16)
            if i<3:rule(im,(x+35,858,x+401,858),TEAL if p>.4+i*.1 else BORDER,3)
            node(im,x,858,label,"",a,TEAL,str(i+1))
        text(im,"Same idempotency key → same receipt",960,960,28,MUTED,align="center",alpha=phase(p,.65,.12))
        self.ui_view(im,"receipt",p,.47,"An execution receipt is recorded",
                     ["Only the synthetic schedule changes.",
                      "Opening cash: 120,000 BDT.",
                      "Target projection: 30,000 BDT."])
        self.ui_view(im,"readback",p,.73,"Read the committed state back",
                     ["Atomic read-back is verified by the UI.",
                      "40,000 BDT remains due on 7 Nov.",
                      "Same key returns the original receipt."])

    def draw_security(self,im:Image.Image,p:float)->None:
        panel(im,(120,348,996,944),"#14274E",BORDER)
        text(im,"Permission boundary",155,380,43,INK,True)
        rows=[("Read + explain","MODEL ALLOWED",TEAL),("Project + compare","MODEL ALLOWED",TEAL),
              ("Draft reminder","MODEL ALLOWED",TEAL),("Approve action","HUMAN ONLY",AMBER),
              ("Execute action","GATED SANDBOX",AMBER)]
        for i,(label,status,color) in enumerate(rows):
            a=phase(p,.08+i*.075,.15);y=476+i*86
            text(im,label,155,y,33,INK,alpha=a)
            text(im,status,959,y+3,24,color,True,"right",a)
            if i<4:rule(im,(155,y+55,960,y+55),BORDER,1)
        text(im,"Snapshot-bound proposals",1059,381,43,INK,True)
        paragraph(im,"Business • Policy • Source rows\nTarget date • Sandbox state",1061,459,33,735,MUTED,False,1.65,phase(p,.12,.16))
        pill(im,"Changed details invalidate the action",1060,605,AMBER,26)
        text(im,"Evidence chain",1060,705,36,INK,True)
        xs=[1104,1264,1424,1584,1744]
        for i,x in enumerate(xs):
            a=phase(p,.36+i*.06,.12)
            if i<len(xs)-1:rule(im,(x+30,796,x+128,796),TEAL if a>.5 else BORDER,3)
            node(im,x,796,["Plan","Approve","Consent","Execute","Receipt"][i],"",a,TEAL,str(i+1))
        text(im,"Local export — not third-party certification",1430,913,27,MUTED,align="center",alpha=phase(p,.63,.14))
        self.ui_view(im,"activity",p,.58,"Permission events form an evidence trail",
                     ["Compare → approval → consent → execute.",
                      "Each event carries its permission boundary.",
                      "Export and check the local hash chain."])

    def draw_assistant(self,im:Image.Image,p:float)->None:
        reveal(im,push_screen(self.screens["main"],p),120,350,phase(p,.06,.19))
        pill(im,"LOCAL DEMO",1300,360,TEAL,27)
        entries=[("Four scoped tools","Read, project, compare, draft."),
                 ("No model authority","Cannot approve or execute."),
                 ("Optional live AI","Owner key + message consent.")]
        for i,(title,body) in enumerate(entries):
            a=phase(p,.15+i*.15,.18);y=445+i*151
            text(im,title,1303,y,36,INK,True,alpha=a)
            paragraph(im,body,1303,y+59,29,470,MUTED,alpha=a)
        text(im,"Live-model evaluation pending",1303,931,26,AMBER,alpha=phase(p,.62,.14))

    def draw_verification(self,im:Image.Image,p:float)->None:
        cards=[("BACKEND TESTS",30,"passed",TEAL),("DETERMINISTIC CASES",18,"of 18 passed",BLUE),
               ("BROWSER CHECKS",2,"Desktop + mobile",AMBER)]
        for i,(label,value,body,color) in enumerate(cards):
            a=phase(p,.06+i*.14,.2);x=120+i*574;y=364+int(34*(1-a))
            if a<=0:continue
            panel(im,(x,y,x+532,y+456),"#14274E",color)
            text(im,label,x+28,y+32,26,color,True,alpha=a)
            text(im,str(round(value*a)),x+266,y+126,126,color,True,"center",a)
            text(im,body,x+266,y+332,35,INK,True,"center",a)
        paragraph(im,"These results verify synthetic correctness and safety.\nReal-world SME outcomes and production readiness remain to be evaluated.",120,873,30,1680,MUTED,False,1.55,phase(p,.54,.18))

    def draw_closing(self,im:Image.Image,p:float)->None:
        text(im,"Financial participation.",960,361,81,INK,True,"center",phase(p,.04,.2))
        text(im,"Owner in control.",960,474,81,TEAL,True,"center",phase(p,.15,.2))
        labels=["Records","Cash gap","Plans","Approval","Sandbox","Evidence"]
        for i,label in enumerate(labels):
            x=225+i*294;a=phase(p,.26+i*.065,.14)
            if i<5:rule(im,(x+34,733,x+260,733),TEAL if a>.5 else BORDER,3)
            node(im,x,733,label,"",a,TEAL,str(i+1))
        text(im,"Next: SME usability testing + live-model evaluation",960,914,33,MUTED,align="center",alpha=phase(p,.69,.14))

    def draw_screenshot(self,im:Image.Image,p:float)->None:
        reveal(im,self.screens["main"],200,341,phase(p,.05,.24))


def infer_kind(scene:dict[str,Any],index:int)->str:
    aliases={"title":"product","cashflow":"timeline","cash-flow":"timeline","options":"comparison",
             "approve":"workflow","evidence":"security","validation":"verification","close":"closing"}
    requested=scene.get("scene_kind") or scene.get("kind")
    if requested:return aliases.get(requested,requested)
    kinds=["problem","product","waterfall","records","timeline","comparison","workflow","execution",
           "security","assistant","verification","closing"]
    return kinds[index] if index<len(kinds) else "closing"


def ffmpeg_path(given:str|None)->str:
    if given:return given
    candidates=[Path("C:/Users/User/AppData/Local/Temp/lla-ffmpeg-validation/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"),
                APP/"tmp/video-reference-analysis/packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"]
    for candidate in candidates:
        if candidate.exists():return str(candidate)
    return "ffmpeg"


def load_scenes(source:Path,preview:bool=False)->tuple[dict[str,Any],list[Scene]]:
    payload=json.loads(source.read_text(encoding="utf-8-sig"))
    scene_data=payload["scenes"] if isinstance(payload,dict) else payload
    result=[]
    for i,data in enumerate(scene_data):
        duration=float(data.get("duration",data.get("duration_seconds",float(data.get("end_seconds",10))-float(data.get("start_seconds",0)))))
        if duration<=0:raise ValueError(f"Non-positive duration for {data.get('id',i)}")
        result.append(Scene(data,duration,infer_kind(data,i)))
    if preview:
        chosen=[0,2,5,6]
        result=[Scene(scene_data[i],3.25,infer_kind(scene_data[i],i)) for i in chosen if i<len(scene_data)]
    return payload,result


def write_contact(scenes:list[Scene],destination:Path)->None:
    destination.parent.mkdir(parents=True,exist_ok=True)
    cols=3;cellw,cellh=640,390
    sheet=Image.new("RGB",(cols*cellw,math.ceil(len(scenes)/cols)*cellh),"#080F2E")
    for i,scene in enumerate(scenes):
        frame=scene.render(scene.duration*.8)
        frame.save(destination.parent/f"scene-{i+1:02d}.png")
        frame=frame.resize((640,360),Image.Resampling.LANCZOS)
        x=i%cols*cellw;y=i//cols*cellh
        sheet.paste(frame,(x,y))
        text(sheet,f"{i+1:02d}  {scene.kind}",x+13,y+365,18,MUTED)
    sheet.save(destination)


def build_audio(scenes:list[Scene],payload:dict[str,Any],voice_arg:str|None,ffmpeg:str,work:Path)->Path|None:
    global_voice=voice_arg or payload.get("narration_audio") or payload.get("voice_file")
    if global_voice:
        candidate=resolve_path(global_voice)
        if not candidate.exists():raise FileNotFoundError(candidate)
        return candidate
    per_scene=[s.data.get("voice_file") or s.data.get("audio") for s in scenes]
    if not any(per_scene):return None
    if not all(per_scene):raise ValueError("Provide a voice file for every scene or a global narration track.")
    paths=[]
    for i,(scene,voice) in enumerate(zip(scenes,per_scene)):
        candidate=resolve_path(voice)
        if not candidate.exists():raise FileNotFoundError(candidate)
        lead=float(scene.data.get("voice_lead_seconds",0))
        if candidate.suffix.lower()==".wav":
            with wave.open(str(candidate),"rb") as audio:
                audio_seconds=audio.getnframes()/audio.getframerate()
            if audio_seconds+lead>scene.duration+.025:
                raise ValueError(f"Scene {scene.data.get('id',i)} is shorter than its narration; update timings instead of clipping speech.")
        padded=work/f"scene-audio-{i+1:02d}.wav"
        filters=f"adelay={round(lead*1000)}:all=1,apad" if lead>0 else "apad"
        subprocess.run([ffmpeg,"-y","-loglevel","error","-i",str(candidate),"-af",filters,
                        "-t",str(scene.duration),"-ar","48000","-ac","2",str(padded)],check=True)
        paths.append(padded)
    listing=work/"audio-concat.txt"
    listing.write_text("\n".join("file '"+str(p).replace("\\","/").replace("'","'\\''")+"'" for p in paths),encoding="utf-8")
    joined=work/"narration-joined.wav"
    subprocess.run([ffmpeg,"-y","-loglevel","error","-f","concat","-safe","0","-i",str(listing),"-c","copy",str(joined)],check=True)
    return joined


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenes",type=Path,default=PRODUCTION/"script/scenes.json")
    parser.add_argument("--output",type=Path,default=HERE/"motion-preview.mp4")
    parser.add_argument("--voice",help="Complete narration audio; no voice is generated or substituted.")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--preview",action="store_true",help="13-second silent motion proof with four scene types.")
    parser.add_argument("--contact-sheet",type=Path)
    parser.add_argument("--frames-only",action="store_true")
    parser.add_argument("--fps",type=int,default=25)
    parser.add_argument("--preset",default="fast")
    parser.add_argument("--crf",type=int,default=20)
    args=parser.parse_args()
    payload,scenes=load_scenes(args.scenes,args.preview)
    contact=args.contact_sheet or HERE/"frames/contact-sheet.png"
    write_contact(scenes,contact)
    if args.frames_only:
        print(f"Wrote {len(scenes)} frames and {contact}",flush=True);return
    args.output.parent.mkdir(parents=True,exist_ok=True)
    work=HERE/"work";work.mkdir(exist_ok=True)
    ffmpeg=ffmpeg_path(args.ffmpeg)
    voice=None if args.preview else build_audio(scenes,payload,args.voice,ffmpeg,work)
    silent=args.output.with_name(args.output.stem+"-silent.mp4") if voice else args.output
    cmd=[ffmpeg,"-y","-hide_banner","-loglevel","error","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}",
         "-r",str(args.fps),"-i","-","-an","-c:v","libx264","-preset",args.preset,"-crf",str(args.crf),
         "-pix_fmt","yuv420p","-movflags","+faststart",str(silent)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    total=sum(s.duration for s in scenes);elapsed=0.;frames=0;started=time.perf_counter()
    try:
        for i,scene in enumerate(scenes):
            n=round(scene.duration*args.fps)
            print(f"Rendering {i+1}/{len(scenes)}: {scene.data.get('id',scene.kind)} ({n} frames)",flush=True)
            for j in range(n):
                t=j/args.fps
                frame=scene.render(t)
                footer(frame,i,len(scenes),(elapsed+t)/total,args.preview)
                proc.stdin.write(frame.tobytes())
                frames+=1
            elapsed+=n/args.fps
    finally:
        proc.stdin.close()
        status=proc.wait()
    if status:raise RuntimeError(f"FFmpeg rendering exited {status}")
    if voice:
        subprocess.run([ffmpeg,"-y","-hide_banner","-loglevel","error","-i",str(silent),"-i",str(voice),
                        "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","192k",
                        "-af","apad","-t",f"{elapsed:.3f}","-movflags","+faststart",str(args.output)],check=True)
    report={"output":str(args.output.resolve()),"frames":frames,"duration_seconds":elapsed,"fps":args.fps,
            "width":W,"height":H,"render_seconds":round(time.perf_counter()-started,2),
            "voice_source":str(voice) if voice else None,"preview":args.preview,
            "fresh_ui_assets":[str(p) for p in ASSETS.glob("*.png")],
            "financial_fixture":"Synthetic Shapla Services; documented exact integer-paisa calculations"}
    args.output.with_suffix(".render.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__":
    main()
