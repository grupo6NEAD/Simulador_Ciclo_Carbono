# app.py — Visual fiel ao mock + MATEMÁTICA (caixas variam com o tempo)
import math
import dash
from dash import dcc, html, Input, Output, State, ALL, ctx
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from plotly.subplots import make_subplots
from dash_bootstrap_templates import template_from_url  # opcional p/ theme no Graph
# import dash_ag_grid as dag  # (opcional; pode remover se não usar tabela)

dbc_css = "https://cdn.jsdelivr.net/gh/AnnMarieW/dash-bootstrap-templates/dbc.min.css"

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY, dbc.icons.FONT_AWESOME, dbc_css]
)
server = app.server


INTERVAL_MS = 200  # 200 ms → base de cálculo do dt

SUBSTEP_MAX_YEARS = 0.2 # Passo máximo por subpasso RK4 (em anos). 0.2 = 2/10 de ano.

# Quantos pontos manter no histórico do gráfico temporal
MAX_HISTORY_LEN = 2000


# ======================= 1) LAYOUT ESTÁTICO (SEU MOCK) =======================
# Caixas (posições e tamanhos-base — NÃO alterei)
boxes = {
    "A":  {"name":"Atmosfera (750)",                 "cx":0.500, "cy":0.900, "w":0.230, "h":0.090, "fill":"rgba(169,169,169,0.95)"},
    "V":  {"name":"Vegetação (610)",                 "cx":0.100, "cy":0.770, "w":0.165, "h":0.085, "fill":"rgba(50,205,50,0.50)"},
    "S":  {"name":"Solos (1.500)",                   "cx":0.100, "cy":0.540, "w":0.185, "h":0.100, "fill":"rgba(50,205,50,0.50)"},
    "Os": {"name":"Superfície do Oceano e Biota Marinha (1.020)",    "cx":0.950, "cy":0.795, "w":0.260, "h":0.105, "fill":"rgba(0,191,255,0.45)"},
    "Od": {"name":"Oceano Profundo (38.100)",        "cx":0.950, "cy":0.560, "w":0.300, "h":0.115, "fill":"rgba(0,191,255,0.45)"},
    "F":  {"name":"Combustíveis Fósseis (4.000)",    "cx":0.660, "cy":0.350, "w":0.295, "h":0.085, "fill":"rgba(210,105,30,0.45)"},
    "R":  {"name":"Rochas sedimentares (100.000.000)","cx":0.100,"cy":0.170, "w":0.500, "h":0.185, "fill":"rgba(210,105,30,0.45)"},
}

def rect_from_box(b):  # (x0,y0,x1,y1)
    cx, cy, w, h = b["cx"], b["cy"], b["w"], b["h"]
    return cx-w/2, cy-h/2, cx+w/2, cy+h/2

def anchor_point_from_rect(rect, side, gap=0.010):
    x0,y0,x1,y1 = rect
    if side=="L":  return (x0-gap, (y0+y1)/2)
    if side=="R":  return (x1+gap, (y0+y1)/2)
    if side=="T":  return ((x0+x1)/2, y1+gap)
    if side=="B":  return ((x0+x1)/2, y0-gap)
    raise ValueError("side must be L/R/T/B")

def _metrics(rects, key):
    """Retorna métricas úteis da caixa: L,R,T,B,cx,cy."""
    x0,y0,x1,y1 = rects[key]
    return {
        "L": x0, "R": x1,
        "B": y0, "T": y1,
        "cx": (x0+x1)/2.0,
        "cy": (y0+y1)/2.0,
    }

def _eval_axis(spec, rects):
    """
    Converte um “spec” em coordenada x OU y.
    Aceita:
      - float/int → valor fixo
      - (ref, attr) ou (ref, attr, offset)
          ref: chave da caixa ("A","V","S","Os","Od","F","R")
          attr: "L","R","T","B","cx","cy"
      - {"op":"mid"/"max"/"min", "items":[spec,...], "offset":float opcional}
    """
    # valor numérico direto
    if isinstance(spec, (int, float)):
        return float(spec)

    # tupla (ref, attr[, offset])
    if isinstance(spec, tuple):
        if len(spec) == 2:
            ref, attr = spec; offset = 0.0
        elif len(spec) == 3:
            ref, attr, offset = spec
        else:
            raise ValueError("spec tuple inválido")
        m = _metrics(rects, ref)
        return m[attr] + float(offset)

    # dict com operações
    if isinstance(spec, dict):
        op = spec.get("op")
        items = spec.get("items", [])
        vals = [_eval_axis(s, rects) for s in items]
        base = None
        if op == "mid":
            if len(vals) != 2:
                raise ValueError("mid requer 2 items")
            base = 0.5*(vals[0]+vals[1])
        elif op == "max":
            base = max(vals)
        elif op == "min":
            base = min(vals)
        else:
            raise ValueError(f"operação desconhecida: {op}")
        return base + float(spec.get("offset", 0.0))

    raise ValueError(f"spec inválido: {spec}")

def reset_history():
    return init_history()


def _resolve_via(v, rects):
    """
    Converte um item de 'vias' em (x,y).
    Aceita:
      - (x,y) numéricos (compatível com o que você já usa)
      - {"x": <spec>, "y": <spec>} dinâmico
    """
    if isinstance(v, dict) and "x" in v and "y" in v:
        return (_eval_axis(v["x"], rects), _eval_axis(v["y"], rects))
    # compatibilidade com (x,y) fixos:
    return v

def init_history():
    """Histórico inicial para o gráfico temporal."""
    return {"t": [0.0], **{r: [Y0[r]] for r in RES_ORDER}}

def push_history(hist, t, y):
    """Acrescenta um ponto ao histórico e faz trimming para não crescer infinito."""
    hist = hist or init_history()
    hist["t"].append(float(t))
    for r in RES_ORDER:
        hist.setdefault(r, []).append(float(y[r]))
    # limita comprimento
    keys = ["t"] + RES_ORDER
    for k in keys:
        if len(hist[k]) > MAX_HISTORY_LEN:
            hist[k] = hist[k][-MAX_HISTORY_LEN:]
    return hist

def res_pretty_name(r):
    return {
        "A":  "Atmosfera",
        "V":  "Vegetação",
        "S":  "Solos e Animais",
        "Os": "Superfície do Oceano e Biota Marinha",
        "Od": "Oceano profundo",
        "F":  "Combustíveis fósseis",
        "R":  "Rochas sedimentares",
    }.get(r, r)



# Setas (SEU ARROWS — NÃO alterei)
ARROWS = [
    # A <-> V
    ("A","L","V","R","Fotossíntese (121,5)",            [], (-0.001, 0.012)),

    # Resp. autotrófica: cotovelo alinhado em x = centro de V, y = centro de A
    ("V","T","A","L","Respiração autotrófica (60)",
        [ {"x": ("V","cx"), "y": ("A","cy")} ],
        ( 0.010, 0.010)
    ),

    # Desmatamento: coluna vertical à esquerda do bloco mais à esquerda; 
    # 1º cotovelo na altura do centro de V; 2º próximo ao topo de A (+0.015)
    ("V","L","A","T","Desmatamento (0)",
        [
            {
                "x": {"op":"min", "items":[("A","L"),("V","L"),("S","L"),("R","L")], "offset": -0.005},
                "y": ("V","cy")
            },
            {
                "x": {"op":"min", "items":[("A","L"),("V","L"),("S","L"),("R","L")], "offset": -0.005},
                "y": ("A","T", 0.015)
            }
        ],
        ( 0.035,-0.010)
    ),

    # V -> S (sem via)
    ("V","B","S","T","Decomposição (61)",               [], ( 0.000, 0.000)),

    # S -> A: cotovelo em x = centro de A; y = centro de S
    ("S","R","A","B","Respiração heterotrófica (60)",
        [ {"x": ("A","cx"), "y": ("S","cy")} ],
        ( 0.055,-0.012)
    ),

    # A -> Os: cotovelo pouco à direita da borda direita de A; y = centro de Os
    ("A","R","Os","L","Difusão A–O (92)",
        [ {"x": ("A","R", 0.010), "y": ("Os","cy")} ],
        ( 0.015, 0.012)
    ),

    # Os -> A: cotovelo em x = centro de Os; y = centro de A
    ("Os","T","A","R","Difusão O–A (90)",
        [ {"x": ("Os","cx"), "y": ("A","cy")} ],
        (-0.015, 0.000)
    ),

    # Os -> Od: coluna vertical externa à direita dos dois oceanos (max(R) + 0.10)
    ("Os","R","Od","R","Circulação Oₛ→O_d (102)",
        [
            {"x": {"op":"max", "items":[("Os","R"),("Od","R")], "offset": 0.10}, "y": ("Os","cy")},
            {"x": {"op":"max", "items":[("Os","R"),("Od","R")], "offset": 0.10}, "y": ("Od","cy")},
        ],
        ( 0.000,-0.012)
    ),

    # Od -> Os (sem via)
    ("Od","T","Os","B","Circulação O_d→Oₛ (100)",       [], ( 0.000, 0.012)),

    # F -> A (sem via)
    ("F","T","A","B","Indústria (0)",                   [], ( 0.012,-0.010)),

    # Od -> F (sem via)
    ("Od","B","F","R","Formação de combustíveis (0)",   [], ( 0.000,-0.010)),

    # Od -> R: cotovelo em x = centro de Od; y = centro de R (preserva o “desenho”)
    ("Od","B","R","R","Sedimentação (0,05)",
        [ {"x": ("Od","cx"), "y": ("R","cy")} ],
        ( 0.012,-0.015)
    ),

    # R -> S (sem via)
    ("R","T","S","B","Erosão (0,05)",                   [], (-0.090, 0.012)),
]


ARROW_COLOR_NAT = "rgb(255,215,0)"   # dourado
ARROW_COLOR_HUM = "rgb(135,206,250)"     # azul (processos humanos)

LINE_WIDTH = 2.2
HEAD_SIZE  = 1.05
HEAD_WIDTH = 2.4
GAP = 0.010
LABEL_OFF = 0.014

def poly_path(points):
    if not points: return ""
    seg = [f"M {points[0][0]} {points[0][1]}"]
    for (x,y) in points[1:]:
        seg.append(f"L {x} {y}")
    return " ".join(seg)

def midpoint_with_normal(points, d_perp=(0.0,0.0)):
    if len(points) < 2: return points[0]
    mid_idx = (len(points)-1)//2
    x0,y0 = points[mid_idx]
    x1,y1 = points[mid_idx+1]
    mx,my = (x0+x1)/2, (y0+y1)/2
    vx,vy = (x1-x0, y1-y0)
    nx,ny = (-vy, vx)
    nl = (nx*nx+ny*ny)**0.5 or 1.0
    nx,ny = nx/nl, ny/nl
    return mx + nx*(LABEL_OFF + d_perp[0]), my + ny*(LABEL_OFF + d_perp[1])

# ======================= 2) DINÂMICA (SUAS EQUAÇÕES) =======================
# Estoques iniciais (GtC) — valores do seu modelo
Y0 = {"A":750.0, "V":610.0, "S":1580.0, "Os":1020.0, "Od":38100.0, "F":4000.0, "R":100_000_000.0}
RES_ORDER = ["A","V","S","Os","Od","F","R"]
TOTAL_CARBON = sum(Y0.values())

# 13 processos (nome igual aos sliders) → (origem j, destino i, F0)
PROCS = [
    ("Fotossíntese",               "A","V", 121.5),
    ("Respiração autotrófica",     "V","A", 60.0),
    ("Desmatamento",               "V","A", 0.0),
    ("Decomposição",               "V","S", 61.0),
    ("Respiração heterotrófica",   "S","A", 60.0),
    ("Difusão A–O",                "A","Os",92.0),
    ("Difusão O–A",                "Os","A",90.0),
    ("Circulação Oₛ→O_d",          "Os","Od",102.0),
    ("Circulação O_d→Oₛ",          "Od","Os",100.0),
    ("Indústria",                  "F","A",0.0),
    ("Formação de combustíveis",   "Od","F",0.0),
    ("Sedimentação",               "Od","R",0.05),
    ("Erosão",                     "R","S",0.05),
]

# Fluxo-semente (em GtC/ano) para processos com F0=0
SEED_FLOW = {
    "Desmatamento": 50.0,             # em p = +1 → ~1 GtC/ano
    "Indústria": 50.0,                # idem
    "Formação de combustíveis": 10.0 # bem lento (escala geológica)
}


# a0 por processo: a0_name["Respiração autotrófica"] = F0 / y_j
a0_name = {}
for name, j, i, F0 in PROCS:
    a0_name[name] = (F0 / Y0[j]) if Y0[j] > 0 else 0.0


# Ganho exponencial e epsilon para processos nulos
THETA = math.log(2.0)     # p = +1 → ×2 ; p = -1 → ×0.5

def a_effective(p_by_name, y_state):
    """
    Retorna a_ij por processo (dict: name -> a_ij).
    - Se F0>0: a = a0 * exp(theta*p)
    - Se F0=0: a = (F_seed / y_j) * max(0, exp(theta*p) - 1)
    """
    out = {}
    for name, j, i, F0 in PROCS:
        p = float(p_by_name.get(name, 0.0))
        if F0 > 0:
            out[name] = a0_name[name] * math.exp(THETA * p)
        else:
            seed = SEED_FLOW.get(name, 0.1)
            yj = y_state.get(j, 0.0)
            a_seed = (seed / yj) if yj > 0 else 0.0
            rel = max(0.0, math.exp(THETA * p) - 1.0)  # 0 em p=0
            out[name] = a_seed * rel
    return out

# nome -> (i,j) (você já tem PROC_NAME_TO_PAIR; vamos reaproveitar)
PROC_NAME_TO_PAIR = {name: (i, j) for (name, j, i, _F0) in PROCS}

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def parse_speed(val, default=1.0):
    try:
        v = float(val)
    except Exception:
        return default
    # limita a um intervalo razoável para evitar dt enorme
    return clamp(v, 0.0, 50.0)   # 0..50 anos/s


def fluxes_by_name(a_eff_by_name, y_state, human_F=None):
    """
    Retorna F por processo: dict[name] = a_name * y_j,
    exceto para processos humanos, onde F = valor digitado (GtC/ano).
    """
    human_F = human_F or {}
    F_name = {}

    for name, j, i, _F0 in PROCS:
        if name in HUMAN_PROCS:
            # usa o input do usuário (>=0), default 0
            try:
                f = float(human_F.get(name, 0.0))
            except Exception:
                f = 0.0
            F_name[name] = max(0.0, f)
        else:
            aij = a_eff_by_name[name]
            F_name[name] = aij * y_state[j]

    return F_name


def sum_fluxes_by_pair(F_name):
    """Soma fluxos de processos que compartilham o mesmo (i,j)."""
    F_pair = {}
    for name, F in F_name.items():
        pair = PROC_NAME_TO_PAIR[name]  # (i,j)
        F_pair[pair] = F_pair.get(pair, 0.0) + F
    return F_pair


def dydt_from_flux(F):
    din = {r:0.0 for r in RES_ORDER}; dout = {r:0.0 for r in RES_ORDER}
    for (i,j), val in F.items():
        din[i]  += val
        dout[j] += val
    return {r: din[r] - dout[r] for r in RES_ORDER}

def rk4_step(y, p_by_name, dt_years, human_F_by_name=None):
    def f(state):
        a_eff_name = a_effective(p_by_name, state)     # a por processo (10 processos)
        F_name     = fluxes_by_name(a_eff_name, state, human_F=human_F_by_name)
        F_pair     = sum_fluxes_by_pair(F_name)        # soma por (i,j) p/ derivada
        return dydt_from_flux(F_pair)

    k1 = f(y)
    y2 = {r: y[r] + 0.5*dt_years*k1[r] for r in RES_ORDER}
    k2 = f(y2)
    y3 = {r: y[r] + 0.5*dt_years*k2[r] for r in RES_ORDER}
    k3 = f(y3)
    y4 = {r: y[r] + dt_years*k3[r] for r in RES_ORDER}
    k4 = f(y4)

    yn = {r: y[r] + (dt_years/6.0)*(k1[r]+2*k2[r]+2*k3[r]+k4[r]) for r in RES_ORDER}

    # clamps + conservação
    for r in RES_ORDER:
        if yn[r] < 0: yn[r] = 0.0
    s = sum(yn.values())
    if s > 0:
        corr = TOTAL_CARBON / s
        yn = {r: yn[r]*corr for r in RES_ORDER}
    return yn

def integrate_substeps(y, p_by_name, human_F_by_name, dt_total_years, dt_max=SUBSTEP_MAX_YEARS):
    """Integra y avançando dt_total_years usando subpassos RK4 de tamanho <= dt_max."""
    if dt_total_years <= 0.0:
        return y
    n = max(1, math.ceil(dt_total_years / dt_max))
    dt = dt_total_years / n
    state = y
    for _ in range(n):
        state = rk4_step(state, p_by_name, dt, human_F_by_name=human_F_by_name)
    return state


# ======================= 3) REDESENHO DO DIAGRAMA (DINÂMICO) =======================
# —— Escala das caixas pelo estoque atual (área ∝ y)
AREA_POWER = 0.5     # w,h ∝ (y/y0)^(0.5)  → área ∝ y
SCALE_MIN = 0.60     # limite inferior de escala (evita caixas sumirem)
SCALE_MAX = 1.60     # limite superior (evita explodirem)

def dynamic_rects(y):
    rects = {}
    for key, b in boxes.items():
        s = (y[key] / Y0[key]) ** AREA_POWER if Y0[key] > 0 else 1.0
        s = max(SCALE_MIN, min(SCALE_MAX, s))
        w = b["w"] * s
        h = b["h"] * s
        cx, cy = b["cx"], b["cy"]
        rects[key] = (cx - w/2, cy - h/2, cx + w/2, cy + h/2)
    return rects  # dict[key] -> (x0,y0,x1,y1)

def scale_of(key, y):
    """Mesmo fator de escala usado nas caixas (área ∝ y)."""
    if Y0[key] <= 0:
        return 1.0
    s = (y[key] / Y0[key]) ** AREA_POWER
    return max(SCALE_MIN, min(SCALE_MAX, s))

FS_BASE = 13
FS_MIN  = 8
FS_MAX  = 28
WRAP_S_THRESHOLD = 0.85   # abaixo disso, quebra em 2 linhas
PAD_SCALE = 0.92          # pequena folga para não colar na borda

def label_text_and_fs(key, valor, y, rect):
    # Nome base (sem o valor inicial entre parênteses)
    base = boxes[key]["name"]
    if "(" in base:
        base = base.split("(")[0].strip()

    # Valor
    val_str = f"{int(round(valor))} GtC"

    # Fonte escala com o tamanho da caixa (como já estava)
    s = scale_of(key, y)
    fs = int(round(FS_BASE * s * PAD_SCALE))
    fs = max(FS_MIN, min(FS_MAX, fs))

    # Forças específicas:
    if key == "Os":
        # quebra boa em 2 linhas para o nome + 3ª linha para o valor
        base_wrapped = "Superfície do Oceano e<br>Biota Marinha"
        return f"<b>{base_wrapped}</b><br><b>({val_str})</b>", fs

    if key == "V":
        # Vegetação sempre em duas linhas (nome em cima, valor embaixo)
        return f"<b>{base}</b><br><b>({val_str})</b>", fs

    # Demais caixas: mesma heurística “que estava boa”
    one_line = f"{base} ({val_str})"
    if s < WRAP_S_THRESHOLD or len(one_line) >= 24:
        text = f"<b>{base}</b><br><b>({val_str})</b>"
    else:
        text = f"<b>{one_line}</b>"

    return text, fs





def fmt_flux(x):
    """Formata fluxo com vírgula decimal: >=1 com 1 casa; <1 com 2 casas."""
    s = f"{x:.1f}" if abs(x) >= 1 else f"{x:.2f}"
    return s.replace(".", ",")

def fmt_speed(v):
    v = float(v)
    s = str(int(v)) if v.is_integer() else f"{v:.1f}"
    return s.replace(".", ",")

def fmt_years(t):
    try:
        t = float(t)
    except Exception:
        t = 0.0
    return str(int(t))




# Mapa: nome do processo → (i, j) para buscarmos F_{i<-j}
PROC_NAME_TO_PAIR = {name: (i, j) for (name, j, i, _F0) in PROCS}


def make_figure(y, arrow_labels=None, speed=None, elapsed_years=None):
    rects = dynamic_rects(y)
    shapes, ann = [], []

    # caixas 
    for key, b in boxes.items():
        x0,y0,x1,y1 = rects[key]
        shapes.append(dict(type="rect", xref="x", yref="y",
                           x0=x0, x1=x1, y0=y0, y1=y1,
                           line=dict(color="black", width=1.2),
                           fillcolor=b["fill"]))
    
     
        box_text, fs = label_text_and_fs(key, y[key], y, rects[key])
        ann.append(dict(
            x=(x0+x1)/2, y=(y0+y1)/2, xref="x", yref="y",
            showarrow=False, text=box_text,
            font=dict(size=fs, color="#0b0b0b"),
            xanchor="center", yanchor="middle",
            align="center"
        ))  


    # setas (mesmas vias/rotas; apenas recalculo o ponto de toque na borda das caixas redimensionadas)
    for idx, (src, sside, dst, dside, label, vias, nudge) in enumerate(ARROWS):
        s = anchor_point_from_rect(rects[src], sside, GAP)
        e = anchor_point_from_rect(rects[dst], dside, GAP)
        pts = [s] + ([_resolve_via(v, rects) for v in (vias or [])]) + [e]

        # rótulo que será exibido (dinâmico se vier de fora)
        use_label = (arrow_labels[idx] if arrow_labels else label)

        # base do nome do processo (sem o "(...)")
        base_name = use_label.split("(")[0].strip()
        if "(" in use_label:
            base, rest = use_label.split("(", 1)
            label_bold = f"<b>{base.strip()}</b> ({rest}"
        else:
            label_bold = f"<b>{use_label}</b>"
            
        is_human = base_name in HUMAN_PROCS
        line_col = ARROW_COLOR_HUM if is_human else ARROW_COLOR_NAT

        # caminho da seta
        shapes.append(dict(
            type="path", xref="x", yref="y",
            path=poly_path(pts),
            line=dict(color=line_col, width=LINE_WIDTH)
            ))  

        # cabeça da seta
       
        x0, y0 = pts[-2]; x1, y1 = pts[-1]
        ann.append(dict(
            x=x1, y=y1, ax=x0, ay=y0,
            xref="x", yref="y", axref="x", ayref="y",
            text="", showarrow=True, arrowhead=3,
            arrowsize=HEAD_SIZE, arrowwidth=HEAD_WIDTH,
            arrowcolor=line_col
            ))



        # rótulo da seta (mantém chip claro; legível no fundo escuro)
        lx, ly = midpoint_with_normal(pts, d_perp=nudge)
        ann.append(dict(
            x=lx, y=ly, xref="x", yref="y", showarrow=False,
            text=label_bold,
            font=dict(size=11, color="#111"),
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="rgba(0,0,0,0.15)", borderwidth=1, borderpad=2
            ))
        
    fig = go.Figure()
    fig.update_layout(
        height=820,
        margin=dict(l=18,r=18,t=28,b=18),
        paper_bgcolor="rgb(54,54,54)",   # fundo escuro
        plot_bgcolor="rgb(54,54,54)",    # fundo escuro
        xaxis=dict(visible=False, range=[0,1], fixedrange=True),
        yaxis=dict(visible=False, range=[0,1], fixedrange=True, scaleanchor="x", scaleratio=1),
        shapes=shapes, annotations=ann,
        title=None
    )
    return fig


def make_timeseries_split_figure(hist):
    t = hist.get("t", [])

    # Subplots: 1 linha, 2 colunas; painel da direita com eixo-Y secundário
    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{}, {"secondary_y": True}]],
        column_widths=[0.60, 0.40],
        subplot_titles=("Ciclo rápido (A, V, S, Os)", "Ciclo lento (Od, F, R)")
    )

    # --- Ciclo rápido (coluna 1) ---
    for r in ["A", "V", "S", "Os"]:
        fig.add_trace(
            go.Scatter(x=t, y=hist.get(r, []), mode="lines",
                       name=res_pretty_name(r), line=dict(width=2)),
            row=1, col=1
        )

    # --- Ciclo lento (coluna 2) ---
    # Od e F no eixo primário (esquerdo do painel direito)
    for r in ["Od", "F"]:
        fig.add_trace(
            go.Scatter(x=t, y=hist.get(r, []), mode="lines",
                       name=res_pretty_name(r), line=dict(width=2)),
            row=1, col=2, secondary_y=False
        )
    # R no eixo secundário (direito do painel direito)
    fig.add_trace(
        go.Scatter(x=t, y=hist.get("R", []), mode="lines",
                   name=res_pretty_name("R") + " (eixo dir.)", line=dict(width=2)),
        row=1, col=2, secondary_y=True
    )

    # Eixos e layout
    fig.update_xaxes(title_text="Tempo (anos)", rangemode="tozero", row=1, col=1)
    fig.update_xaxes(title_text="Tempo (anos)", rangemode="tozero", row=1, col=2)

    fig.update_yaxes(title_text="Estoque (GtC)", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title_text="Estoque (GtC)", rangemode="tozero", row=1, col=2, secondary_y=False)
    fig.update_yaxes(title_text="Rochas sedimentares (GtC)", rangemode="tozero", row=1, col=2, secondary_y=True, showgrid=False)

    fig.update_layout(
        height=820,
        margin=dict(l=18, r=18, t=40, b=18),
        paper_bgcolor="rgb(54,54,54)",
        plot_bgcolor="rgb(54,54,54)",
        legend=dict(orientation="h", yanchor="bottom", y=1.10, xanchor="left", x=0),
        font=dict(color="#eeeeee")
    )
    fig.update_xaxes(color="#eeeeee", gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.15)")
    fig.update_yaxes(color="#eeeeee", gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.15)")
    return fig




# ======================= 4) PROCESSOS: sliders x humanos =======================
# Todos os 13 (na mesma ordem do seu modelo)
PROCESSOS_TODOS = [
    "Fotossíntese",
    "Respiração autotrófica",
    "Desmatamento",              # ← humano (input direto)
    "Decomposição",
    "Respiração heterotrófica",
    "Difusão A–O",
    "Difusão O–A",
    "Circulação Oₛ→O_d",
    "Circulação O_d→Oₛ",
    "Indústria",                 # ← humano (input direto)
    "Formação de combustíveis",  # ← humano (input direto)
    "Sedimentação",
    "Erosão",
]

HUMAN_PROCS = ["Desmatamento", "Indústria", "Formação de combustíveis"]
PROCESSOS_SLIDERS = [p for p in PROCESSOS_TODOS if p not in HUMAN_PROCS]  # 10 processos

def slider_comp(nome, i):
    return html.Div([
        html.Label(f"{i:02d}. {nome}", style={"color": "#fff"}),
        dcc.Slider(
            min=-2, max=2, step=0.01, value=0,
            marks={-2:"-2",-1:"-1",0:"0",1:"1",2:"2"},
            tooltip={"placement":"bottom","always_visible":False},
            id={"type":"proc-slider","name":nome}
        )
    ], style={"marginBottom":"16px"})

# Sliders apenas para os 10 processos não-humanos
SLIDERS = [slider_comp(n, i+1) for i, n in enumerate(PROCESSOS_SLIDERS)]


# ======================= 5) LAYOUT (apenas para tornar dinâmico) =======================
fig_init = make_figure(Y0)

app.layout = dbc.Container(
    fluid=True,
    style={"backgroundColor": "rgb(54,54,54)"},
    children=[
        # estados/relógio (iguais aos seus)
        dcc.Store(id="state-y", data=Y0),
        dcc.Store(id="state-t", data=0.0),
        dcc.Store(id="state-hist", data=init_history()),
        dcc.Store(id="state-view", data="diagram"),  # 'diagram' ou 'series'
        


        dcc.Interval(id="tick", interval=INTERVAL_MS, n_intervals=0),

        dbc.Row(
            className="g-2",  # espaçamento entre colunas
            children=[
                # -------- Coluna ESQUERDA: sliders dos 13 processos --------
                # -------- Coluna ESQUERDA: painel Processos Humanos + sliders --------
dbc.Col(
    width=12, lg=3,
    children=[
        # Painel Processos Humanos (inputs diretos)
        html.Div(
            [
                html.Div(
                    [
                        html.I(className="fa-solid fa-people-group", style={"fontSize":"18px","marginRight":"8px"}),
                        html.Span("Processos Humanos"),
                    ],
                    id="title-human",
                    style={
                        "display":"inline-flex","alignItems":"center","gap":"8px",
                        "padding":"10px 14px",
                        "border":"2px solid rgba(0,0,0,0.15)","borderRadius":"12px",
                        "background":"linear-gradient(180deg, rgba(255,255,255,0.96), rgba(245,245,245,0.96))",
                        "boxShadow":"0 1px 3px rgba(0,0,0,0.08)",
                        "fontFamily":"Georgia, 'Times New Roman', serif","fontWeight":"600",
                        "fontSize":"20px","letterSpacing":"0.2px","margin":"8px 0 10px 0"
                    }
                ),

                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Desmatamento"),
                        dbc.Input(id="inp-desmatamento", type="number", min=0, step=0.1, value=0),
                        dbc.InputGroupText("GtC/ano"),
                    ],
                    size="sm", className="mb-2"
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Indústria"),
                        dbc.Input(id="inp-industria", type="number", min=0, step=0.1, value=0),
                        dbc.InputGroupText("GtC/ano"),
                    ],
                    size="sm", className="mb-2"
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Formação de combustíveis"),
                        dbc.Input(id="inp-formcomb", type="number", min=0, step=0.01, value=0),
                        dbc.InputGroupText("GtC/ano"),
                    ],
                    size="sm", className="mb-3"
                ),
            ],
            id="panel-human",
            style={"padding":"8px 8px 0 0"}
        ),

        # Título + SLIDERS dos 10 processos restantes (como já estava)
        html.Div(
            [
                html.I(className="fa-solid fa-sliders", style={"fontSize":"18px", "marginRight":"8px"}),
                html.Span("Processos da Natureza"),
            ],
            id="title-proc",
            style={
                "display":"inline-flex","alignItems":"center","gap":"8px",
                "padding":"10px 14px",
                "border":"2px solid rgba(0,0,0,0.15)","borderRadius":"12px",
                "background":"linear-gradient(180deg, rgba(255,255,255,0.96), rgba(245,245,245,0.96))",
                "boxShadow":"0 1px 3px rgba(0,0,0,0.08)",
                "fontFamily":"Georgia, 'Times New Roman', serif","fontWeight":"600",
                "fontSize":"20px","letterSpacing":"0.2px","margin":"8px 0 6px 0"
            }
        ),
        html.Div(
            SLIDERS,
            id="panel-sliders",
            style={
                "maxHeight": "calc(100vh - 140px)","overflowY": "auto","padding": "8px 8px 8px 0",
            },
        ),
    ],
    style={"minWidth":"300px","borderRight":"1px solid #eee","paddingLeft":"8px"},
),


                # -------- Coluna DIREITA: velocidade + figura --------
                dbc.Col(
                    width=12, lg=9,
                    children=[
                        # (seu slider de velocidade e readout, como já estão)
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.I(className="fa-solid fa-gauge-high",
                                               style={"fontSize":"18px", "marginRight":"8px"}),
                                        html.Span("Velocidade da simulação (anos/s)"),
                                    ],
                                    id="title-speed",
                                    style={
                                        "display":"inline-flex",
                                        "alignItems":"center",
                                        "gap":"8px",
                                        "padding":"10px 14px",
                                        "border":"2px solid rgba(0,0,0,0.15)",
                                        "borderRadius":"12px",
                                        "background":"linear-gradient(180deg, rgba(255,255,255,0.96), rgba(245,245,245,0.96))",
                                        "boxShadow":"0 1px 3px rgba(0,0,0,0.08)",
                                        "fontFamily":"Georgia, 'Times New Roman', serif",
                                        "fontWeight":"600",
                                        "fontSize":"20px",
                                        "letterSpacing":"0.2px",
                                        "margin":"8px 0 6px 0"
                                    }
                                ),

                                dbc.InputGroup(
                                    [
                                        dbc.Input(
                                            id="inp-speed",
                                            type="number",
                                            min=0,          # 0 = pausa
                                            step=0.1,
                                            value=1.0,      # padrão 1 ano/s
                                            placeholder="anos/s"
                                        ),
                                        dbc.InputGroupText("anos/s"),
                                    ],
                                    size="sm",
                                    className="mt-2"
                                ),
                                html.Small("Use decimais; 0 pausa a simulação.", style={"opacity":0.8, "color":"#fff"})
                            ],
                            style={"padding":"8px 8px 0 8px"}
                        ),
                        
                        html.Div(
                            dbc.Button(
                                id="btn-reset",
                                n_clicks=0,
                                color="danger",
                                children="Reiniciar simulação",
                                className="mt-2"
                            ),
                            style={"padding":"8px 8px 0 8px"}
                        ),

                        html.Div(
                            id="speed-readout",
                            style={"textAlign":"right", "padding":"0 8px 8px 8px", "fontWeight":"500", "color":"#eeeeee"}
                        ),
                        
                        html.Div(
                            dbc.Button(
                                id="btn-toggle-view",
                                n_clicks=0,
                                outline=True,
                                color="secondary",
                                children="Ver gráfico temporal"
                            ),
                            style={"textAlign":"right", "padding":"0 8px 8px 8px"}
                        ),

                        
                        # Título estilizado da figura (dinâmico)
                        html.Div(
                            [
                                html.I(className="fa-solid fa-diagram-project",
                                       style={"fontSize":"18px", "marginRight":"8px"}),
                                html.Span(id="fig-title-text")  # será preenchido via callback
                            ],
                            id="title-figure",
                            style={
                                "display":"inline-flex",
                                "alignItems":"center",
                                "gap":"8px",
                                "padding":"10px 14px",
                                "border":"2px solid rgba(0,0,0,0.15)",
                                "borderRadius":"12px",
                                "background":"linear-gradient(180deg, rgba(255,255,255,0.96), rgba(245,245,245,0.96))",
                                "boxShadow":"0 1px 3px rgba(0,0,0,0.08)",
                                "fontFamily":"Georgia, 'Times New Roman', serif",
                                "fontWeight":"600",
                                "fontSize":"20px",
                                "letterSpacing":"0.2px",
                                "margin":"0 8px 8px 8px",
    }
),


                        dcc.Graph(
                            id="fig-diagrama",
                            figure=fig_init,
                            config={"displayModeBar": False},
                            style={"height": "820px"}
                        ),
                    ],
                ),
              ],
            ),
        ],
    )


# ======================= 6) CALLBACKS =======================
YEARS_PER_SECOND = 1.0  # 1 ano por segundo (200 ms → 0.2 ano)
DT_YEARS = YEARS_PER_SECOND * (200/1000.0)

@app.callback(
    Output("state-y", "data"),
    Output("state-t", "data"),
    Output("state-hist", "data"),
    Output({"type":"proc-slider","name":ALL}, "value"),   # <-- NOVO
    Output("inp-desmatamento", "value"),                  # <-- NOVO
    Output("inp-industria", "value"),                     # <-- NOVO
    Output("inp-formcomb", "value"),                      # <-- NOVO
    Output("inp-speed", "value"),                         # <-- NOVO                        
    Input("tick", "n_intervals"),
    Input("btn-reset", "n_clicks"),
    State("state-y", "data"),
    State({"type":"proc-slider","name":ALL}, "value"),
    State("state-t", "data"),
    # novos States já existentes dos processos humanos:
    State("inp-desmatamento", "value"),
    State("inp-industria", "value"),
    State("inp-formcomb", "value"),
    # novo: velocidade por input
    State("inp-speed", "value"),
    State("state-hist", "data"),
    prevent_initial_call=False
)
def on_tick(n, n_reset, ydata, pvalues, t_elapsed,
            v_desm, v_ind, v_form,
            v_speed, hist):

    # --- RESET COMPLETO: estoques/tempo/histórico + todos os controles ---
    if ctx.triggered_id == "btn-reset":
       zero_sliders = [0.0] * len(PROCESSOS_SLIDERS)
       return (
           Y0,                 # state-y
           0.0,                # state-t
           init_history(),     # state-hist
           zero_sliders,       # sliders naturais
           0.0,                # inp-desmatamento
           0.0,                # inp-industria
           0.0,                # inp-formcomb
           1.0,                # inp-speed
        )



    # p apenas para os processos com slider
    p_by_name = {PROCESSOS_SLIDERS[i]: float(pvalues[i]) for i in range(len(PROCESSOS_SLIDERS))} if pvalues else {}
    y = {k: float(v) for k,v in ydata.items()} if isinstance(ydata, dict) else Y0

    # velocidade (anos/s) vinda do input
    speed = parse_speed(v_speed, default=1.0)

    # dt do tick (anos)
    dt_years = speed * (INTERVAL_MS/1000.0)  # INTERVAL_MS já está = 200

    # valores humanos (GtC/ano)
    human_F = {
        "Desmatamento": float(v_desm or 0),
        "Indústria": float(v_ind or 0),
        "Formação de combustíveis": float(v_form or 0),
    }

    
    # integra com subpassos para estabilidade em velocidades altas
    y_next = integrate_substeps(y, p_by_name, human_F_by_name=human_F, dt_total_years=dt_years)


    # acumula tempo
    t_prev = float(t_elapsed) if t_elapsed is not None else 0.0
    t_next = t_prev + dt_years
    hist_next = push_history(hist, t_next, y_next)
    
    # garantimos que o 4º output (sliders) seja sempre uma lista do tamanho certo
    if isinstance(pvalues, (list, tuple)) and len(pvalues) == len(PROCESSOS_SLIDERS):
        sliders_out = list(pvalues)
    else:
        sliders_out = [0.0] * len(PROCESSOS_SLIDERS)


    return (
        y_next, t_next, hist_next,
        sliders_out,          # <-- aqui
        dash.no_update,       # inp-desmatamento
        dash.no_update,       # inp-industria
        dash.no_update,       # inp-formcomb
        dash.no_update,       # inp-speed
        )





@app.callback(
    Output("fig-diagrama", "figure"),
    Output("fig-title-text", "children"),
    Input("state-y", "data"),
    Input({"type": "proc-slider", "name": ALL}, "value"),
    Input("state-t", "data"),
    Input("inp-desmatamento", "value"),
    Input("inp-industria", "value"),
    Input("inp-formcomb", "value"),
    Input("inp-speed", "value"),
    Input("state-view", "data"),   # <-- NOVO
    State("state-hist", "data"),   # <-- NOVO (State basta)
)
def update_figure_and_title(ydata, pvalues, t_elapsed,
                            v_desm, v_ind, v_form,
                            v_speed, view_mode, hist):
    y = {k: float(v) for k, v in ydata.items()} if isinstance(ydata, dict) else Y0
    speed = parse_speed(v_speed, default=1.0)
    elapsed = float(t_elapsed) if t_elapsed is not None else 0.0

    # Título base
    title_txt = (
        "Ciclo do carbono"
        + f" — Velocidade: {fmt_speed(speed)} anos/s"
        + f" — Tempo: {fmt_years(elapsed)} anos"
    )

    # Escolhe visualização
    if (view_mode or "diagram") == "series":
        # gráfico temporal
        fig = make_timeseries_split_figure(hist or init_history())
        title_txt += " — Visualização: Série temporal"
        return fig, title_txt

    # diagrama (como antes)
    p_by_name = {PROCESSOS_SLIDERS[i]: float(pvalues[i]) for i in range(len(PROCESSOS_SLIDERS))} if pvalues else {}
    a_eff_name = a_effective(p_by_name, y)
    human_F = {
        "Desmatamento": float(v_desm or 0),
        "Indústria": float(v_ind or 0),
        "Formação de combustíveis": float(v_form or 0),
    }
    F_name = fluxes_by_name(a_eff_name, y, human_F=human_F)

    arrow_labels = []
    for (_src, _sside, _dst, _dside, label, _vias, _nudge) in ARROWS:
        base = label.split("(")[0].strip()
        if base in F_name:
            arrow_labels.append(f"{base} ({fmt_flux(F_name[base])} GtC/ano)")
        else:
            arrow_labels.append(label[:-1] + " GtC/ano)" if label.endswith(")") else label + " (GtC/ano)")

    fig = make_figure(y, arrow_labels=arrow_labels)
    title_txt += " — Visualização: Diagrama"
    return fig, title_txt


@app.callback(
    Output("state-view", "data"),
    Input("btn-toggle-view", "n_clicks"),
    Input("btn-reset", "n_clicks"),
    State("state-view", "data"),
    prevent_initial_call=False
)
def toggle_view(n_toggle, n_reset, cur):
    cur = cur or "diagram"
    trigger = ctx.triggered_id
    if trigger == "btn-reset":
        # Ao resetar, sempre volta para o diagrama
        return "diagram"
    if trigger == "btn-toggle-view":
        if not n_toggle:
            return cur
        return "series" if cur == "diagram" else "diagram"
    return cur

@app.callback(
    Output("btn-toggle-view", "children"),
    Input("state-view", "data"),
    prevent_initial_call=False
)
def sync_view_label(cur):
    cur = cur or "diagram"
    return "Ver gráfico temporal" if cur == "diagram" else "Ver diagrama"


@app.callback(
    Output("speed-readout", "children"),
    Input("inp-speed", "value")
)
def show_speed(v_speed):
    speed = parse_speed(v_speed, default=1.0)
    return f"Velocidade: {fmt_speed(speed)} anos/s"


if __name__ == "__main__":
    app.run(debug=True)
