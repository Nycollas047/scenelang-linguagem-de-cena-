"""Vocabulário fechado da linguagem (Fase 0).

Regra: este arquivo só cresce por proposta aprovada. Todo termo aceito pela
linguagem existe aqui, com a sua tradução em frase visual (hoje em português).
"""

# Direções: vetor 2D (x para a direita, y para baixo) e frase visual.
DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "up_left": (-1, -1),
    "up_right": (1, -1),
    "down_left": (-1, 1),
    "down_right": (1, 1),
    "toward_camera": (0, 0),
    "away": (0, 0),
}

DIRECTION_PT = {
    "up": "para cima",
    "down": "para baixo",
    "left": "para a esquerda",
    "right": "para a direita",
    "up_left": "para cima e para a esquerda",
    "up_right": "para cima e para a direita",
    "down_left": "para baixo e para a esquerda",
    "down_right": "para baixo e para a direita",
    "toward_camera": "na direção da câmera",
    "away": "na direção contrária à câmera",
}

# Planos, em ordem de desenho (do fundo para a frente).
PLANES = ("background", "midground", "foreground")
PLANE_PT = {
    "foreground": "No primeiro plano",
    "midground": "No plano médio",
    "background": "Ao fundo",
}

KINDS = (
    "character",
    "creature",
    "prop",
    "structure",
    "terrain",
    "sky",
    "effect",
    "light_source",
    "vehicle",
)

GRIDS = ("golden", "thirds")
CANVAS_SHAPES = ("rect", "circle", "ellipse")

LIGHT_ROLES = ("key", "rim", "backlight", "ambient", "fill")
LIGHT_ROLE_PT = {
    "key": "luz principal",
    "rim": "rim light",
    "backlight": "contraluz",
    "ambient": "luz ambiente",
    "fill": "luz de preenchimento",
}

# Níveis de brilho e de saturação (usados pelo orçamento de foco).
LEVELS = ("low", "normal", "high", "max")
SATURATION_LEVELS = ("muted", "normal", "high", "max")

ANGLES = {
    "low": "levemente de baixo para cima",
    "eye": "na altura dos olhos",
    "high": "de cima para baixo",
    "top": "vista totalmente de cima",
}
LENSES = {
    "wide": "grande angular cinematográfica",
    "normal": "lente normal",
    "tele": "teleobjetiva, com perspectiva comprimida",
}

# Âncoras: ponto relativo dentro da caixa da entidade (fx, fy), y para baixo.
# "tip" e "base" são calculadas pela orientação (ver layout.anchor_xy).
ANCHORS = {
    "center": (0.5, 0.5),
    "top": (0.5, 0.0),
    "bottom": (0.5, 1.0),
    "left": (0.0, 0.5),
    "right": (1.0, 0.5),
    "head": (0.5, 0.08),
    "face": (0.5, 0.12),
    "shoulder": (0.5, 0.25),
    "feet": (0.5, 0.97),
    "tip": None,
    "base": None,
}
DYNAMIC_ANCHORS = ("tip", "base")
ANCHOR_PT = {
    "center": "o centro",
    "top": "o topo",
    "bottom": "a parte inferior",
    "left": "o lado esquerdo",
    "right": "o lado direito",
    "head": "a cabeça",
    "face": "o rosto",
    "shoulder": "o ombro",
    "feet": "os pés",
    "tip": "a ponta",
    "base": "a base",
}

# Regiões da grade 3x3 (linha_coluna) e pontos de interesse (interseções).
ROW_NAMES = ("top", "mid", "bottom")
COL_NAMES = ("left", "center", "right")
POINT_NAMES = ("pt_ul", "pt_ur", "pt_ll", "pt_lr")
POINT_PT = {
    "pt_ul": "no ponto de interesse superior esquerdo da grade",
    "pt_ur": "no ponto de interesse superior direito da grade",
    "pt_ll": "no ponto de interesse inferior esquerdo da grade",
    "pt_lr": "no ponto de interesse inferior direito da grade",
}

# Predicados aceitos em `assert` e a forma dos seus argumentos.
PREDICATES = (
    "above",
    "below",
    "left_of",
    "right_of",
    "inside",
    "near",
    "count",
    "visible",
    "facing",
    "brightest",
    "focal_single",
)

REJECTION_TAGS = ("direção", "luz", "proporção", "estilo", "anatomia", "enquadramento")

SPIRAL_DIRECTIONS = ("cw", "ccw")
