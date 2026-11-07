# Referência rápida da linguagem (v0.3)

## Estrutura de uma cena

| Chave | Papel |
|---|---|
| `scene`, `version` | nome e versão |
| `canvas` | `ratio`, `shape` (rect, circle, ellipse), `pixel_grid` (células na largura, 4–512) |
| `grid` | `kind`: golden (áurea) ou thirds (terços) |
| `style` | `base` e `mix` (percentuais somando 100) |
| `intent` | `focal` (referência), `emotion`, `story` |
| `colors` | cores nomeadas, usadas como `"@nome"` |
| `palette` | `dominant`, `accent`, `accent_use`, `notes`; e `mode` (fixed, model_picks), `space` (rgb, cmyk, hsl), `count`, `harmony`, `colors`, `constraints` (contrast_min, min_distance, max_colors), `proposal` |
| `guides` | `mode` (fixed, model_proposes), `subject`, `canon`, `axis`, `lines`, `margin`, `proposal` |
| `background` | `mode` (scene, chromakey), `key` (auto ou cor), `alpha` (chroma, difference), `tolerance`, `edge`, `rules` |
| `atmosphere` | `mood {name, level}`, `weather`, `wind {direction, strength}` |
| `materials`, `detail` | biblioteca de materiais; orçamento de detalhe por zona |
| `camera`, `lights`, `gaze` | enquadramento, luz, ordem do olhar |
| `entities` | `id`, `kind`, `plane`, `label`, `desc`, `box` ou `at`+`size`, `orient`, `brightness`, `saturation`, `tags`, `character`, `material`, `parts`, `detail`, `wind_parts`, `translucent` |
| `asserts` | condições de layout (sem imagem) |
| `verify` | medições na imagem gerada |
| `lock` | partes a manter iguais à versão anterior |
| `extends`, `import` | herança de cena e bibliotecas |

## Cores

`"#rrggbb"`, `{rgb: [0-255 ×3]}`, `{cmyk: [0-100 ×4]}`, `{hsl: [0-360, 0-100, 0-100]}` ou `"@nome"`.
Harmonias: monochromatic, analogous, complementary, triadic, free.

## Vocabulário fechado

- **Direções** (de quem vê): up, down, left, right, up_left, up_right, down_left, down_right, toward_camera, away
- **Planos:** background, midground, foreground
- **Cânones de proporção:** chibi (2), stylized (4), child (5), realistic (7,5), heroic (8) ou `{heads_tall: N}`
- **Linhas-guia:** head_top, eye, chin, shoulder, waist, knee, baseline
- **Moods:** serene, tense, melancholic, epic, mysterious, joyful, ominous, cozy · **clima:** clear, rain, snow, fog, storm, dust · **vento:** calm, low, normal, high, max
- **Materiais (base):** metal, stone, cloth, leather, skin, wood, glass, water, crystal, fur, paper, bone, scales, feathers, chitin, shell, rubber, plastic, ceramic, wool · **acabamento:** polished, matte, scratched, oxidized, wet, rough, glossy, mossy, dusty
- **Regras de fundo:** no_spill, no_shadow_on_key, no_gradient, subject_inside_frame

## Asserts (layout) e verify (imagem)

- `asserts`: above, below, left_of, right_of, inside, near, count, visible, facing, brightest, focal_single
- `verify`: max_colors(N), grid_aligned(N), symmetric(vertical, mín), fit_guides(tol), palette_match(ΔE), chroma_clean(), no_spill(), margin(células)

## Protocolo de planejamento

1. `scenelang plan cena.yaml` → JSON com o que o modelo deve responder (cores faltantes, linhas, regras).
2. O modelo responde um YAML: `palette: {papel: [valores]}` e/ou `guides: {linha: y}`.
3. `scenelang plan-apply cena.yaml proposta.yaml` valida (harmonia, contraste, cânone) e grava.

## Personagem (`entities[].character`)

Atributos descritivos e independentes. Nada é deduzido de `heritage` (texto livre do autor, até 80 caracteres).

| Campo | Valores |
|---|---|
| `age_group` | child, teen, young_adult, adult, middle_aged, elder |
| `skin` | `tone` 1–10 (escala Monk, cor de referência embutida) ou `color` exata; `undertone` cool/neutral/warm/olive; `finish` matte/dewy/weathered/smooth; `marks` freckles, moles, scars, vitiligo, birthmark, wrinkles, tattoos, blush, sun_spots |
| `hair` | `texture` straight/wavy/curly/coily, `length` bald…very_long, `density`, `color`, `style` (texto) |
| `facial_hair` | `type` beard/mustache/stubble/goatee/sideburns/beard_and_mustache, `length`, `color`, `style` |
| `eyes`, `face` | cor e formato dos olhos; formato do rosto, nariz, lábios, mandíbula |
| `body` | `build`, `height`, `shoulders`, `waist`, `hips`, `limbs`, `posture`, `proportion` (chibi/stylized/realistic/heroic, avisa se destoa de `guides.canon`) |
| `features` | parte (ears, horns, tail, wings, claws…) → texto livre |

A cor da pele entra nas cores de referência da escolha automática da chave do fundo.

## Pose em graus (`entities[].pose`, v0.4)
Evita anatomia impossível: cada junta recebe um ângulo e a linguagem rejeita o que o corpo humano não faz.
- `body_yaw`: -180..180 (0 de frente, 90 perfil para a direita da imagem, 180 de costas).
- `joints`: `neck`, `spine`, `{left,right}_{shoulder,elbow,wrist,hip,knee,ankle}`; número = eixo principal, mapa = eixos
  (`flex`, `abduct`, `rotate`, `turn`, `twist`, `tilt`, `side`). Esquerda/direita são do personagem; 0° = neutro.
- `hold`: o que cada mão/pé segura (`left_hand`, `right_hand`, `left_foot`, `right_foot`).
- Fora da faixa: erro com `fix` (limita ao máximo); perto do limite: aviso; corpo de costas sem girar o pescoço: aviso.
- `profile`: perfil anatômico (`human_adult`, padrão; `stylized`, faixas +25%). Referencial e perfis de rig: seção «Pose em camadas (v0.7)».

## Onde as coisas ficaram na imagem (v0.4)
`scenelang locate cena.yaml imagem.png [--boxes achados.json]` mede a caixa de cada entidade na imagem pronta, compara com a declarada,
acusa **espelhamento** e reavalia os asserts de posição (`left_of`, `above`, `inside`...) sobre as caixas medidas.
- `signature: ["#a42625", "#551014"]` (na entidade, 1 a 3 cores): o código acha esses pixels sem modelo de visão; serve quando a cor é distintiva.
- `--boxes`: caixas `{id: [x, y, w, h]}` de quem olhou a imagem; `locate cena.yaml --form` gera o pedido para um modelo de visão.
- `scenelang render` desenha o boneco de construção da `pose` dentro da caixa da entidade; `scenelang pose cena.yaml <id> --out figura.png`
  gera a folha grande em 3 vistas (como declarada, de frente, de perfil).
- Boneco de construção: cabeça = esfera alongada, pescoço e membros = cilindros afunilados, ombros e joelhos = esferas, tronco e pélvis = caixas
  paralelas, mãos = ovos, pés = cunhas. Tracejado = parte de trás; a elipse do cilindro fica mais aberta quando o membro aponta para a câmera.
  D (laranja) = lado direito do personagem, E (azul) = esquerdo.

## Laço de correção automático (v0.5)
`scenelang correct cena.yaml imagem.png [--boxes achados.json] --out-dir rodada1` mede a imagem (verify, posição, espelhamento) e grava:
- `relatorio.json`: o registro da rodada (medições, caixas declaradas × medidas, IoU), que serve de dado de avaliação;
- `cena.next.yaml`: a cena com `corrections` (uma frase afirmativa por falha, dizendo o que estava errado e onde deve ficar),
  `priority_boost` nos asserts de posição reprovados e `history`;
- `prompt_next.txt`: o prompt da próxima rodada, com a seção "CORREÇÕES DA VERSÃO ANTERIOR".
Código de saída 0 se tudo passou, 1 se há falhas. `corrections` é uma lista de textos (até 12) e pode ser escrita à mão.

## Um arquivo só (v0.5)
`scenelang pack cena.yaml --out-dir pacote [--only text|guide|single]` escolhe o formato pelo que o modelo de destino aceita:
| Modelo aceita | Use | Arquivos |
|---|---|---|
| só texto | `--only text` | `prompt.txt` |
| texto + uma imagem de referência | `--only guide` | `guia.png` + `prompt_com_guia.txt` |
| um único anexo (chat com visão) | `--only single` | `cena_unica.png`: guia no alto e o prompt escrito embaixo |
O guia mostra retângulos por plano e o manequim de cada entidade com `pose`; `--labels` escreve o nome de cada elemento (padrão: só em `single`).
O PNG leva prompt e cena nos metadados: `scenelang unpack cena_unica.png [prompt|yaml|cena]` recupera.

## Relatório de perdas (v0.4)
`scenelang compile cena.yaml --loss [all]` lista o que o backend não leva (ou leva só aproximado) ao gerador, com os níveis da seção «Perdas (v0.7)»;
`--strict` falha com código 3 se há parte sem tradução ou a cena não tem asserts. O backend `regions` agora leva
intenção, iluminação, detalhes e acabamento no `global_prompt` e as camadas (personagem, pose, material, vento) em cada região.

## Tecidos e escamas (em `material`, `parts` ou `materials`)

- Tecido: `fabric` (cotton, linen, silk, satin, wool, velvet, denim, lace, canvas, tulle, leather, burlap, chiffon, felt, tweed, corduroy, suede, fleece, knit, mesh), `weave` (plain, twill, checked, striped, herringbone, polka, floral, embroidered, brocade, quilted, pleated, ribbed, patched), `drape` (stiff, structured, flowing, heavy, clingy, billowing, tattered). `base: cloth` é implícito.
- Escamas: `scales: {pattern, size, edge, sheen, gradient {from,to}, color, coverage}`. `pattern`: overlapping, hexagonal, diamond, plate, granular, keeled, rounded; `size`: tiny…huge; `edge`: smooth, serrated, spiked, rough. `base: scales` é implícito; `coverage` limita às partes citadas.
- Avisos de contradição: lona (canvas) com caimento fluido, granular grande, caimento rígido em peça movida pelo vento.

## Uso por modelos de linguagem

| Comando | Para quê |
|---|---|
| `primer` | cartilha de uma página gerada do vocabulário |
| `vocab [--json]` | todos os vocabulários fechados |
| `new [modelo] [--out F]` | cena inicial: sprite, splash, emblem, character-sheet |
| `validate --fix [--out F]` | aplica correções seguras (typo de valor ou de campo, com `fix` no diagnóstico) |

Formas curtas aceitas (e registradas em `defaults_applied` na API): `canvas: "16:9"`, `style: "texto"`, `grid` ausente (golden), `pixel_grid: "64x64"`, `label` ausente (vem do id), `atmosphere.mood: epic`, `verify: [grid_aligned]`, apelidos em português (`kind: personagem`, `plane: fundo`, `grid: terços`), `chroma_key`, `sheen: strong`, campos de `character` soltos na entidade.
`scenelang.api` oferece `validate`, `fix`, `compile_scene`, `plan`, `primer`, `vocab`, `new` com retorno JSON-serializável.

## Medir e pós-processar (v0.3)

`snap` (grade real, limite de cores, paleta exata, encaixe nas guias, fundo transparente), `sheet-prompt`/`sheet-measure` (variantes lado a lado, medidas por coluna), `verify symmetric(vertical, 0.8, legs)` (só pernas, ignora capa/cabelo ao vento) e avisos de contradição (paleta × descrição, simetria × vento, margem × sujeito).

## Servidor MCP e skill (v0.6)

`scenelang-mcp` é um servidor MCP (stdio) que expõe as mesmas operações da CLI como ferramentas
(`scenelang_primer`, `_new`, `_validate`, `_check_layout`, `_render_schema`, `_pose_sheet`, `_compile`, `_pack`, `_locate`, `_verify`, `_measure`).
O modelo escreve a cena em YAML e chama as ferramentas; os arquivos vão para `out_dir` e os caminhos voltam no resultado.
A skill em `skill/scenelang/SKILL.md` ensina o fluxo e quando entregar cada arquivo.

Instalação: `pip install "scenelang[mcp] @ git+https://github.com/Nycollas047/scenelang-linguagem-de-cena-"`.

Configuração (Claude Desktop, Claude Code, Cursor, etc.):

```json
{"mcpServers": {"scenelang": {"command": "scenelang-mcp"}}}
```

Claude Code: `claude mcp add scenelang -- scenelang-mcp`.


---

# v0.7 — auditoria e robustez

## Hash canônico da cena (`scenelang/canon.py`)
`canon.scene_hash(data)` = SHA-256 do JSON canônico (`canon-v1-sha256`): chaves ordenadas em todos os níveis, listas na ordem original
(a ordem das entidades é a ordem de desenho), `1` e `1.0` iguais, NaN/infinito e tipos sem forma canônica rejeitados (`CanonError`).
`history` e `corrections` ficam fora do hash semântico: mudam a cada rodada sem mudar a cena pedida (`include_transient=True` os inclui).
`relatorio.json` traz `hash_cena` (12 caracteres), `hash_cena_completo` e `hash_algoritmo`. Os hashes de relatórios da v0.5 usavam
`repr(sorted(items))` (só ordenava o nível de cima) e **não** são comparáveis com os atuais.

## Motor de correção (`scenelang/correction/`)
Responsabilidades separadas: detecção (`correct.measure`) → classificação e confiança (`Finding.source`) → instrução (`Rule`) → plano (`plan`)
→ histórico (`CorrectionHistory`) → relatório (`correct.report`).
- Uma `Rule` por tipo de falha, com prioridade, confiança mínima, efeitos colaterais, `post_fix` (comando que conserta a imagem depois) e `build(ctx, finding, attempt)`.
  Cobertura: espelhamento, asserts de posição (`above/below/left_of/right_of/inside/near`), `visible` e todos os verificadores
  (`max_colors`, `grid_aligned`, `palette_match`, `symmetric`, `margin`, `fit_guides`, `chroma_clean`, `no_spill`; há teste que falha se um verificador novo ficar sem regra).
  Nova correção = nova subclasse com `@register`; o resto não muda.
- O plano separa: **aplicadas** (viram `corrections`), **adiadas** (evidência fraca: medição só por cor tem confiança 0,5 < 0,6; ou limite de 12 por rodada)
  e **não resolvidas** (sem regra; instrução já aplicada em 3 rodadas; ou a regra não tem versão mais explícita do texto). Nada genérico é inventado.
- Repetição: cada tentativa escala o texto (versão mais explícita); sem versão nova, a falha vira «não resolvida» com a sugestão de `post_fix`.
- Histórico: rodadas recentes (6) em detalhe; as antigas viram um resumo (`resumo: true`) com contagem por check, aplicadas, imagens e tags.
  `--keep-rounds N` muda o limite. Entradas da v0.5 continuam válidas.

## Pack (`scenelang/pack.py`)
- `pack_result` devolve `{files, manifest, warnings}`; `pacote.json` (formatos com mais de um arquivo) traz hash da cena, SHA-256 de cada arquivo, entidades (id, caixa, cor do `seg`), sobreposições e avisos.
  `--strict` recusa o pacote (e apaga o que gravou) se algo não puder ser preservado.
- Nada some em silêncio: entidade que não entra no guia (`sky`, `terrain`), entidade com menos de 50% visível, tamanho/proporção fora de 256–4096 px e 3:1, fonte sem acentos e metadados grandes viram avisos.
- `unpack --check` (PNG ou pasta) confere hash da cena, ids, prompt e SHA-256 dos arquivos; `single` continua sendo **um arquivo só** (tudo nos metadados do PNG).
- Texto do painel: quebra por largura medida em pixels (nunca corta); rótulos do guia sem colisão e desenhados por último.

## Guia `seg`
Mapa de segmentação **aproximado**: cada entidade é um retângulo chapado (a caixa declarada), **não** uma máscara pixel a pixel.
Cor por entidade determinística e sem colisão (ΔE ≥ 25 até ~25 entidades; mais que isso reduz o limite, nunca repete cor; ids duplicados são erro).
A região onde duas entidades se sobrepõem recebe uma terceira cor própria; a legenda cor → id fica no manifesto e em `prompt_com_guia.txt`.
Estilos previstos e ainda **não** implementados (`mask`, `semantic`, `instance`, `depth`, `parts`) dão erro explícito; o manifesto já marca `geometria: "caixa"` por entidade.

## Locate com estados
Cada entidade sai com um estado: `localizada`, `parcial`, `nao_localizada`, `evidencia_insuficiente` ou `ambigua`, mais `source`
(`assinatura` | `informada` | `nenhuma`), `confidence` e `reason`. Só `localizada` vota no espelhamento e nos asserts de posição.
**Ausência de evidência não é prova de ausência**: cor que não aparece é `evidencia_insuficiente`; só uma caixa `null` informada por quem olhou a imagem vale `nao_localizada`.
Cor espalhada, blocos distantes com a mesma cor ou assinaturas que se confundem dão `ambigua`; caixa cortada pela borda ou com <30% da área declarada dá `parcial`.

## Perdas (v0.7)
Cada chave da cena tem destino declarado por backend (`loss.FATE`): `preserved`, `approx`, `external` (precisa de pós-processamento, guia em imagem etc.),
`unchecked`, `unsupported` (sem destino: bloqueia `--strict`), `lost`, `meta` (controle que não vai ao gerador). `loss.fidelity()` só diz «completa» sem nenhum dos piores.
Backends: `prose`, `json`, `regions` e `compact` (sem PRIORIDADES, ORDEM DO OLHAR e lembrete final: ~20% menos texto, com `gaze` declarado como `lost`).

## Pose em camadas (v0.7)
Representação abstrata (`pose:`) × perfil anatômico (`pose.profile`, `anatomy.py`) × perfil de rig (`rig.py`). Referencial formal em `anatomy.FRAME`
(x direita da imagem, y cima, z para a câmera; `body_yaw` é a única rotação global; juntas locais; left/right do personagem).
`scenelang pose cena.yaml <id> --export unity_humanoid|mixamo|scenelang [--calibration cal.json]` troca os nomes das juntas pelos ossos do destino; **sem calibração a saída vem
marcada `calibrated: false`** (repouso, eixos e sinais de cada rig precisam ser medidos). Avisos de heurística anatômica (perna reta levantada, ombro travado) não são erros: estar dentro das faixas não prova que o corpo faça aquilo.
Corrigido na v0.7: o manequim tinha os sinais da flexão (ombro, quadril, cotovelo, joelho), abdução, inclinação do pescoço/coluna e torção invertidos; só aparecia de perfil ou em torção.

## Incremental, patch e cache
- `scenelang diff A B` / `patch CENA ops.json` / `delta-prompt A B`: patch mínimo (`set/remove/add/append/reorder`, entidades pelo `id`), o que mudou e o que precisa ser reavaliado
  (`deps.delta`: asserts e verificadores afetados; conservador na dúvida), e um prompt de **edição** só com o que mudou (precisa da imagem anterior como entrada).
- Cache em memória (`cache.py`), chave = hash canônico das dependências + versão: leitura da cena e **medição de imagens** (o passo caro, ~1,5 s/1,5 MP). Histórico e correções não invalidam.
- Validar a cena leva ~11 ms e compilar ~2 ms: **a validação não foi tornada incremental** porque não compensa; a economia está em medir, em tokens (prompt de edição) e em não reavaliar o que a edição não toca.

## Benchmark (`scenelang bench`)
`bench plan` grava os prompts dos cinco modos (convencional, completa, compacta, incremental, com_guia) e as métricas offline; `bench record` registra cada geração
(tokens de saída, chamadas, tentativas, custo; com imagem, mede as restrições em código, só medições de confiança ≥ 0,6); `bench report` agrega.
Não chama nenhum gerador; o que não foi medido aparece como «—». Sem `--baseline` o modo convencional é uma linearização **sintética**, marcada como tal.
