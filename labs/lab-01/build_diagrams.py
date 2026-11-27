"""Создание собственных редактируемых схем EduCloud и векторных экспортов."""

from pathlib import Path
from html import escape
import hashlib, json, math

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "diagrams"
C = {
    "ink": "#243047",
    "blue": "#2457a7",
    "green": "#24714c",
    "orange": "#ad5717",
    "purple": "#7050a0",
    "grey": "#64748b",
}


class Scene:
    def __init__(self, name, w, h):
        self.name = name
        self.w = w
        self.h = h
        self.elements = []
        self.tags = {}
        self.connections = []

    def add(self, typ, x, y, w, h, stroke="ink", fill="transparent", **kw):
        ident = f"{self.name}-{len(self.elements)+1:03d}"
        e = dict(
            id=ident,
            type=typ,
            x=x,
            y=y,
            width=w,
            height=h,
            angle=0,
            strokeColor=C.get(stroke, stroke),
            backgroundColor=fill,
            fillStyle="solid",
            strokeWidth=1.8,
            strokeStyle="solid",
            roughness=0,
            opacity=100,
            groupIds=[],
            frameId=None,
            index="a" + str(len(self.elements)).zfill(4),
            seed=1000 + len(self.elements),
            version=1,
            versionNonce=2000 + len(self.elements),
            isDeleted=False,
            boundElements=None,
            updated=0,
            link=None,
            locked=False,
            roundness=None,
        )
        e.update(kw)
        self.elements.append(e)
        return e

    def text(self, text, x, y, w, size=24, color="ink", align="center"):
        return self.add(
            "text",
            x,
            y,
            w,
            len(text.split("\n")) * size * 1.25,
            stroke=color,
            text=text,
            originalText=text,
            fontSize=size,
            fontFamily=2,
            textAlign=align,
            verticalAlign="top",
            containerId=None,
            autoResize=False,
            lineHeight=1.25,
        )

    def rect(
        self,
        tag,
        label,
        x,
        y,
        w,
        h,
        fill="#eff5fd",
        stroke="blue",
        size=24,
        typ="rectangle",
    ):
        e = self.add(typ, x, y, w, h, stroke, fill)
        if tag:
            self.tags[tag] = e["id"]
        lines = len(label.split("\n"))
        self.text(label, x + 8, y + (h - lines * size * 1.25) / 2, w - 16, size, stroke)
        return e

    def border(self, title, x, y, w, h, fill="#ffffff", stroke="grey", size=26):
        self.add("rectangle", x, y, w, h, stroke, fill)
        self.text(title, x + 14, y + 12, w - 28, size, stroke, align="left")

    def actor(self, tag, name, x, y):
        e = self.add("ellipse", x - 16, y, 32, 32)
        self.tags[tag] = e["id"]
        self.line([(x, y + 32), (x, y + 80)])
        self.line([(x - 29, y + 48), (x + 29, y + 48)])
        self.line([(x, y + 80), (x - 25, y + 115)])
        self.line([(x, y + 80), (x + 25, y + 115)])
        self.text(name, x - 90, y + 122, 180, 22)

    def line(self, pts, color="ink", dashed=False, arrow=False, both=False):
        x, y = pts[0]
        points = [[px - x, py - y] for px, py in pts]
        e = self.add(
            "arrow" if arrow else "line",
            x,
            y,
            max(p[0] for p in pts) - min(p[0] for p in pts),
            max(p[1] for p in pts) - min(p[1] for p in pts),
            stroke=color,
            points=points,
            lastCommittedPoint=None,
            startBinding=None,
            endBinding=None,
            startArrowhead="arrow" if both else None,
            endArrowhead="arrow" if arrow else None,
            elbowed=False,
        )
        if dashed:
            e["strokeStyle"] = "dashed"
        return e

    def edge(
        self,
        a,
        b,
        pts,
        label=None,
        at=None,
        color="blue",
        both=False,
        dashed=False,
        size=21,
    ):
        self.line(pts, color, dashed, True, both)
        self.connections.append(
            {"from": a, "to": b, "label": label, "bidirectional": both}
        )
        if label and at:
            x, y, w = at
            ht = len(label.split("\n")) * size * 1.25
            self.add(
                "rectangle",
                x - 4,
                y - 2,
                w + 8,
                ht + 4,
                stroke="#ffffff",
                fill="#ffffff",
                strokeWidth=0,
            )
            self.text(label, x, y, w, size, color)

    def label(self, text, x, y, w, color="grey", size=21):
        self.text(text, x, y, w, size, color, align="left")

    def save(self):
        data = {
            "type": "excalidraw",
            "version": 2,
            "source": "https://excalidraw.com",
            "elements": self.elements,
            "appState": {
                "viewBackgroundColor": "#ffffff",
                "gridSize": None,
                "theme": "light",
                "name": self.name,
                "exportWithDarkMode": False,
            },
            "files": {},
        }
        (OUT / (self.name + ".excalidraw")).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        )
        # Тот же набор векторных элементов, без добавления результата или интерфейса.
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}"><rect width="100%" height="100%" fill="white"/>'
        ]
        for e in self.elements:
            x, y, w, h = e["x"], e["y"], e["width"], e["height"]
            col = e["strokeColor"]
            fill = e["backgroundColor"]
            sw = e["strokeWidth"]
            attrs = f'stroke="{col}" stroke-width="{sw}" fill="{fill if fill!="transparent" else "none"}"'
            if e["strokeStyle"] == "dashed":
                attrs += ' stroke-dasharray="8 6"'
            if e["type"] == "rectangle":
                svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {attrs}/>')
            elif e["type"] == "ellipse":
                svg.append(
                    f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" {attrs}/>'
                )
            elif e["type"] == "text":
                size = e["fontSize"]
                align = e["textAlign"]
                tx = x + w / 2 if align == "center" else x
                anchor = "middle" if align == "center" else "start"
                for i, line in enumerate(e["text"].split("\n")):
                    svg.append(
                        f'<text x="{tx}" y="{y+size+i*size*1.25}" fill="{col}" font-family="Arial, sans-serif" font-size="{size}" text-anchor="{anchor}">{escape(line)}</text>'
                    )
            else:
                pts = [(x + px, y + py) for px, py in e["points"]]
                svg.append(
                    '<polyline points="'
                    + " ".join(f"{px},{py}" for px, py in pts)
                    + f'" {attrs}/>'
                )

                def head(p0, p1):
                    a = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
                    l = 12
                    q1 = (
                        p1[0] - l * math.cos(a - 0.42),
                        p1[1] - l * math.sin(a - 0.42),
                    )
                    q2 = (
                        p1[0] - l * math.cos(a + 0.42),
                        p1[1] - l * math.sin(a + 0.42),
                    )
                    svg.append(
                        f'<polyline points="{q1[0]},{q1[1]} {p1[0]},{p1[1]} {q2[0]},{q2[1]}" stroke="{col}" stroke-width="{sw}" fill="none"/>'
                    )

                if e.get("endArrowhead"):
                    head(pts[-2], pts[-1])
                if e.get("startArrowhead"):
                    head(pts[1], pts[0])
        svg.append("</svg>")
        (OUT / (self.name + ".svg")).write_text("".join(svg))
        return {
            "file": self.name + ".excalidraw",
            "elements": len(self.elements),
            "nodes": self.tags,
            "flows": self.connections,
        }


s = Scene("01_use_case", 1440, 1350)
s.text("EduCloud — варианты использования", 180, 20, 1080, 32)
s.border("Платформа онлайн-обучения EduCloud", 210, 100, 1020, 1070, size=28)
# Овалы в четыре строки по ролям.
case = lambda tag, label, x, y, w=270, h=90, fill="#eff5fd": s.rect(
    tag, label, x, y, w, h, fill=fill, typ="ellipse", size=24
)
case("courses", "Просмотреть\nкурсы", 250, 230)
case("pay", "Оплатить\nкурс", 590, 230)
case("materials", "Скачать\nматериалы", 930, 230)
case("login", "Авторизоваться", 250, 385)
case("archive", "Просмотреть\nархив лекций", 590, 385)
case("discount", "Применить\nскидку", 930, 385, fill="#eef7ef")
case("upload", "Загрузить\nматериал", 250, 590)
case("update", "Обновить\nкурс", 590, 590)
case("stats", "Просмотреть\nстатистику", 930, 590)
case("users", "Управлять\nпользователями", 250, 790)
case("payments", "Управлять\nплатежами", 590, 790)
case("monitor", "Проверить логи\nи метрики", 250, 995, fill="#eef7ef")
case("restart", "Перезапустить\nсервис", 590, 995, fill="#eef7ef")
s.actor("student", "Студент", 90, 200)
s.actor("teacher", "Преподаватель", 90, 575)
s.actor("admin", "Администратор", 90, 775)
s.actor("technician", "Технический\nспециалист", 90, 980)
# Ассоциации идут к верхнему краю овалов, вне тел соседних вариантов.
for actor, y, targets in [
    ("student", 250, [(385, 230), (725, 230), (1065, 230)]),
    ("teacher", 625, [(385, 590), (725, 590), (1065, 590)]),
    ("admin", 825, [(385, 790), (725, 790)]),
    ("technician", 1030, [(385, 995), (725, 995)]),
]:
    for i, (tx, ty) in enumerate(targets):
        lane = ty - 60 + i * 14
        s.line([(120, y), (190, lane), (tx, lane), (tx, ty)], "ink")

s.line([(120, 270), (190, 360), (320, 360), (320, 394)])
s.line([(120, 285), (185, 490), (675, 490), (675, 470)])
s.edge(
    "discount",
    "pay",
    [(1000, 385), (1000, 350), (795, 350), (795, 316)],
    "«extend»\nпри наличии промокода",
    (785, 335, 190),
    color="green",
    dashed=True,
    size=17,
)
s.rect(
    "stripe",
    "«внешняя система»\nStripe",
    540,
    1230,
    300,
    95,
    fill="#eef7ef",
    stroke="green",
)
s.rect(
    "sendgrid",
    "«внешняя система»\nSendGrid",
    950,
    1230,
    300,
    95,
    fill="#eef7ef",
    stroke="green",
)
# Внешняя интеграция через правую свободную полосу.
s.line(
    [(725, 320), (725, 334), (1260, 334), (1260, 1200), (690, 1200), (690, 1230)],
    "green",
)
s.line([(745, 319), (745, 344), (1300, 344), (1300, 1275), (1250, 1275)], "green")
s.label(
    "Защищённые действия —\nпосле входа и проверки\nправ пользователя.",
    905,
    810,
    295,
    size=21,
)
s.label(
    "Зелёным: новая роль,\nпромокод и внешние\nучастники оплаты.",
    905,
    1000,
    300,
    size=21,
)
meta = [s.save()]

s = Scene("02_dfd", 1530, 1300)
s.text("EduCloud — потоки данных", 200, 20, 1120, 32)
s.border("Облачная часть платформы", 270, 100, 1000, 920, fill="#ffffff", stroke="grey")
s.rect(
    "client",
    "Веб-клиент\nМобильное\nприложение",
    20,
    270,
    210,
    120,
    fill="#f1f5f9",
    stroke="ink",
    size=24,
)
s.rect("gateway", "1. API Gateway", 310, 280, 240, 100)
s.rect("auth", "2. Auth Service", 660, 140, 250, 100)
s.rect("course", "3. Course Service", 660, 400, 250, 100)
s.rect("payment", "4. Payment Service", 660, 670, 250, 100)
s.rect("notify", "5. Notification\nService", 980, 820, 250, 100)
# Хранилища: открытые боковые границы через две горизонтальные линии.
for tag, label, x, y in [
    ("postgres", "D1  PostgreSQL\nПользователи\nи курсы", 1010, 150),
    ("redis", "D2  Redis\nСессии и кэш", 1010, 420),
]:
    s.tags[tag] = s.text(label, x, y + 17, 235, 23)["id"]
    s.line([(x, y), (x + 235, y)], "grey")
    s.line([(x, y + 125), (x + 235, y + 125)], "grey")
s.rect(
    "registry",
    "6. Service Registry\nConsul / Eureka",
    310,
    720,
    260,
    120,
    fill="#f4effa",
    stroke="purple",
)
s.rect(
    "sftp",
    "Локальный ЦОД\nSFTP-сервер\nАрхив лекций",
    660,
    1070,
    250,
    110,
    fill="#fff4e8",
    stroke="orange",
    size=22,
)
s.rect("stripe", "Stripe API", 1310, 670, 200, 100, fill="#eef7ef", stroke="green")
s.rect("sendgrid", "SendGrid API", 1310, 820, 200, 100, fill="#eef7ef", stroke="green")
s.edge(
    "client",
    "gateway",
    [(230, 330), (310, 330)],
    "REST /\nответ",
    (225, 263, 90),
    both=True,
    size=18,
)
s.edge(
    "gateway",
    "auth",
    [(480, 280), (480, 190), (660, 190)],
    "Данные входа / JWT",
    (355, 146, 275),
    both=True,
)
s.edge(
    "gateway",
    "course",
    [(550, 350), (600, 350), (600, 450), (660, 450)],
    "Курсы /\nматериалы",
    (455, 414, 165),
    both=True,
    size=20,
)
s.edge(
    "auth",
    "postgres",
    [(910, 190), (1010, 190)],
    "Пользователи",
    (894, 148, 125),
    both=True,
    size=18,
)
s.edge(
    "auth",
    "redis",
    [(840, 240), (950, 315), (1130, 315), (1130, 420)],
    "Сессии",
    (1015, 320, 100),
    both=True,
    size=20,
)
s.edge(
    "course",
    "postgres",
    [(910, 450), (970, 450), (970, 270), (1010, 270)],
    "Курсы",
    (916, 349, 90),
    both=True,
    size=20,
)
s.edge(
    "gateway",
    "payment",
    [(510, 380), (600, 600), (600, 720), (660, 720)],
    "Запрос оплаты / статус",
    (295, 563, 300),
    both=True,
    size=20,
)
s.edge(
    "payment",
    "stripe",
    [(910, 720), (1310, 720)],
    "Платёж / результат",
    (984, 678, 260),
    color="green",
    both=True,
    size=21,
)
s.edge(
    "payment",
    "notify",
    [(790, 770), (790, 870), (980, 870)],
    "Событие оплаты",
    (775, 795, 230),
    size=21,
)
s.edge(
    "notify",
    "sendgrid",
    [(1230, 870), (1310, 870)],
    "Письмо /\nстатус",
    (1225, 801, 95),
    color="green",
    both=True,
    size=18,
)
s.edge(
    "gateway",
    "sftp",
    [(350, 380), (285, 470), (285, 1125), (660, 1125)],
    "Архив / файл\nSFTP в VPN",
    (300, 1050, 320),
    color="orange",
    both=True,
    size=21,
)
s.edge(
    "auth",
    "registry",
    [(660, 220), (620, 270), (620, 780), (570, 780)],
    "Регистрация\nимя и адрес",
    (575, 850, 160),
    color="purple",
    dashed=True,
    size=19,
)
s.edge(
    "course",
    "registry",
    [(720, 500), (720, 610), (540, 610), (540, 720)],
    "Регистрация",
    (654, 553, 170),
    color="purple",
    dashed=True,
    size=19,
)
s.edge(
    "gateway",
    "registry",
    [(430, 380), (430, 720)],
    "Адреса сервисов\nзапрос / ответ",
    (300, 655, 190),
    color="purple",
    dashed=True,
    both=True,
    size=19,
)
s.label(
    "Внутренние данные — синий; внешние API — зелёный;\nгибридный архив — оранжевый; реестр сервисов — фиолетовый.",
    280,
    1228,
    1100,
    size=22,
)
meta.append(s.save())

s = Scene("03_deployment", 1540, 1530)
s.text("EduCloud — схема развёртывания", 220, 20, 1120, 32)
s.border(
    "AWS · Kubernetes · приватная сеть приложений",
    310,
    110,
    1200,
    1110,
    fill="#ffffff",
    stroke="blue",
    size=27,
)
s.rect(
    "client",
    "Клиенты\nБраузер\nMobile App",
    20,
    175,
    240,
    130,
    fill="#f1f5f9",
    stroke="ink",
    size=25,
)
s.rect("lb", "Load Balancer\nALB / Ingress · :443", 760, 160, 340, 100, size=25)
s.rect("gateway", "API Gateway\nМаршрутизация / JWT", 760, 320, 340, 100, size=25)
s.border(
    "Availability Zone 1", 350, 520, 510, 330, fill="#f4f8ff", stroke="blue", size=26
)
s.border(
    "Availability Zone 2", 960, 520, 510, 330, fill="#f4f8ff", stroke="blue", size=26
)
s.rect("auth1", "«Pod»\nAuth Service\nреплика 1", 380, 610, 210, 150, size=24)
s.rect("course1", "«Pod»\nCourse Service\nреплика 1", 620, 610, 210, 150, size=24)
s.rect("auth2", "«Pod»\nAuth Service\nреплика 2", 990, 610, 210, 150, size=24)
s.rect("course2", "«Pod»\nCourse Service\nреплика 2", 1230, 610, 210, 150, size=24)
s.rect("payment", "«Pod»\nPayment Service", 370, 920, 275, 115, size=25)
s.rect("notify", "«Pod»\nNotification Service", 690, 920, 290, 115, size=25)
s.rect(
    "registry",
    "Service Registry\nConsul / Eureka",
    1090,
    920,
    300,
    115,
    fill="#f4effa",
    stroke="purple",
    size=24,
)
s.rect(
    "postgres",
    "«StatefulSet / PV»\nPostgreSQL · :5432",
    370,
    1090,
    300,
    100,
    fill="#f1f5f9",
    stroke="grey",
    size=24,
)
s.rect(
    "redis",
    "«StatefulSet / PV»\nRedis · :6379",
    710,
    1090,
    290,
    100,
    fill="#f1f5f9",
    stroke="grey",
    size=24,
)
s.rect(
    "vpn", "VPN Gateway", 1110, 1090, 280, 100, fill="#fff4e8", stroke="orange", size=25
)
s.rect(
    "stripe",
    "Внешний API\nStripe",
    20,
    920,
    240,
    115,
    fill="#eef7ef",
    stroke="green",
    size=25,
)
s.rect(
    "sendgrid",
    "Внешний API\nSendGrid",
    20,
    1090,
    240,
    115,
    fill="#eef7ef",
    stroke="green",
    size=25,
)
s.border(
    "Локальный ЦОД · архив лекций",
    840,
    1300,
    670,
    210,
    fill="#fffaf4",
    stroke="orange",
    size=27,
)
s.rect(
    "firewall", "Firewall", 870, 1380, 210, 90, fill="#fff4e8", stroke="orange", size=25
)
s.rect(
    "sftp",
    "SFTP Server\nАрхив лекций · :22",
    1180,
    1380,
    300,
    90,
    fill="#fff4e8",
    stroke="orange",
    size=24,
)
s.edge("client", "lb", [(260, 240), (760, 240)], "HTTPS :443", (385, 198, 270), size=24)
s.edge("lb", "gateway", [(930, 260), (930, 320)])
# По одной реплике каждого из двух сервисов в каждой зоне.
for target, tx, route in [
    ("auth1", 485, 450),
    ("course1", 725, 470),
    ("auth2", 1095, 450),
    ("course2", 1335, 470),
]:
    sx = 820 if tx < 900 else 1040
    s.edge(
        "gateway",
        target,
        [(sx, 420), (sx, route), (tx, route), (tx, 610)],
        color="blue",
    )
s.label(
    "HTTP :8080 · по одной реплике Auth и Course в каждой зоне", 350, 865, 1100, size=22
)
s.edge("gateway", "payment", [(760, 370), (330, 370), (330, 975), (370, 975)])
s.edge(
    "gateway",
    "vpn",
    [(1100, 370), (1485, 370), (1485, 1140), (1390, 1140)],
    color="orange",
)
s.label("Архив: SFTP :22", 1110, 1055, 280, color="orange", size=22)
s.edge(
    "payment",
    "stripe",
    [(370, 980), (260, 980)],
    "HTTPS :443",
    (270, 902, 100),
    color="green",
    size=18,
)
s.edge("payment", "notify", [(645, 980), (690, 980)])
s.edge(
    "notify",
    "sendgrid",
    [(835, 1035), (835, 1060), (280, 1060), (280, 1145), (260, 1145)],
    "HTTPS :443",
    (395, 1038, 250),
    color="green",
    size=23,
)
s.edge(
    "vpn",
    "firewall",
    [(1250, 1190), (1250, 1260), (975, 1260), (975, 1380)],
    "IPsec VPN\nSFTP :22 внутри туннеля",
    (1020, 1230, 400),
    color="orange",
    size=23,
)
s.edge("firewall", "sftp", [(1080, 1425), (1180, 1425)], color="orange", both=True)
s.label(
    "PostgreSQL, Redis и реестр —\nобщие зависимости подов.\nВнутренние порты — в приватной сети.",
    350,
    1234,
    530,
    size=20,
)
meta.append(s.save())
# Семантическое описание для проверки соответствия трёх схем.
manifest = {
    "system": "EduCloud",
    "student": "Вахрушев И.А.",
    "group": "25-КМ-ИБ2",
    "diagrams": meta,
    "replicas": {
        "Auth Service": {"AZ1": 1, "AZ2": 1},
        "Course Service": {"AZ1": 1, "AZ2": 1},
        "Payment Service": 1,
        "Notification Service": 1,
    },
    "external_systems": ["Stripe", "SendGrid"],
    "hybrid_archive": {"protocol": "SFTP", "port": 22, "tunnel": "IPsec VPN"},
}
(ROOT / "architecture.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
)
print("Created", len(meta), "diagrams")
