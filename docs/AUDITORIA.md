# Auditoria técnica da v0.5.1 → v0.7.0

Baseline: v0.5.1 (`86da510`) mais o servidor MCP da v0.6.0 (`9b08158`). Resultado: v0.7.0.
Testes: 352 aprovados, 2 ignorados (exemplos que dependem de arquivo externo), 0 reprovados (`pytest -q`).

## A. Relatório de auditoria

| # | Problema | Existia? | Onde | Causa | Solução |
|---|---|---|---|---|---|
| P0 | `correct` só traduz parte das falhas | **Sim** | `correct.py` | Só `max_colors`, `grid_aligned`, `palette_match`, espelhamento, posição e `visible` tinham texto; `symmetric`, `margin`, `fit_guides`, `chroma_clean`, `no_spill`, `near`, `inside` eram medidos e ignorados em silêncio | Pacote `correction/` com `Rule` por falha (todas cobertas, com teste que falha se um verificador novo ficar sem regra), planejador, histórico, relatório; falha sem regra vira «não resolvida» |
| P0 | Instrução que falhou repetia para sempre | **Sim** | `correct.py` | Sem contagem de tentativas | `CorrectionHistory.attempts`; cada tentativa escala o texto; sem versão nova, ou após 3 rodadas, vira «não resolvida» com `post_fix` |
| P0 | Instrução genérica podia piorar a imagem | **Sim, e vi acontecer** | `correct.py` | Medição só por cor (`signature`) gerou «fogueira à esquerda» falso na imagem do sapo mago e a correção foi para o prompt | Confiança por origem (imagem 0,95, caixa informada 0,9, cor 0,5); abaixo de 0,6 a falha é **adiada** e o prompt não muda |
| P1 | `pack`: legibilidade e perdas silenciosas | **Sim** | `pack.py` | Quebra de linha por nº de caracteres (fonte variável); rótulos desenhados dentro do laço e cobertos por caixas seguintes; `sky`/`terrain` fora do guia sem aviso; sem checagem de tamanho | Quebra por largura medida, rótulos por último sem colisão, avisos explícitos, `check_dimensions`, `--strict` |
| P1 | IDs e integridade `pack`/`unpack` | **Parcial** | `pack.py` | Metadados guardavam cena e prompt, mas nada os conferia; `text` não guardava a cena | `pacote.json` (SHA-256 por arquivo, hash da cena, entidades), `cena.yaml`, `unpack --check`; teste de ida e volta `cena → pack → unpack → cena` em 4 formatos × 2 estilos, com unicode |
| P1 | `seg`: ~10 cores fixas | **Sim** | `pack.py` | `SEG_COLORS[index % 10]` | `seg_colors`: cor derivada do hash do id, resolução de colisão por ΔE (≥ 25 até ~25 entidades; abaixo disso reduz o limite, nunca repete), ids duplicados são erro |
| P1 | `seg`: sobreposição escondia entidades | **Sim** | `pack.py` | Pintura em ordem, sem registro | Região de sobreposição com cor própria, `ocultas` (<50% visível) em avisos, legenda cor → id |
| P1 | `seg` é retângulo, não máscara | **Sim (e é limitação conhecida)** | `pack.py` | Só há caixas na cena | Documentado; manifesto marca `geometria: "caixa"`; estilos `mask/semantic/instance/depth/parts` reservados e dão erro explícito |
| P1 | Hash com `repr(sorted(items))` | **Sim** | `correct.py:137` | Ordena só o nível de cima; ordem de chaves aninhadas muda o hash; incluía `history`/`corrections` | `canon.py` (`canon-v1-sha256`); testes de ordem, tipos, unicode, histórico; rodado sobre todos os exemplos |
| P2 | Histórico crescia sem limite | **Sim** | `correct.py` | `history.append` sem teto | Compactação para resumo com contagens, imagens e tags; idempotente; teste de 20 rodadas |
| P2 | `locate`: `source` inconsistente | **Sim** | `locate.py` | `compare` assumia `"informada"` quando faltava a origem | Vocabulário fechado; origem ausente = `desconhecida`, tratada como a mais fraca |
| P2 | `locate`: caixas ruins descartadas sem rastro | **Sim** | `correct.measure` | Filtro `reliable` apagava a entidade | Estados `localizada / parcial / nao_localizada / evidencia_insuficiente / ambigua`, com confiança e motivo; ausência de evidência nunca vira prova de ausência |
| P2 | `locate` dependia de `scipy` sem declarar | **Sim (achado novo)** | `pyproject.toml` | Import em `locate.py`, extras só com pillow/numpy | `scipy` nos extras `image`, `mcp`, `dev` |
| P2 | Pose: referencial e rigs | **Parcial** | `pose.py`, `skeleton.py` | Referencial só em comentários; faixas só para um perfil | `anatomy.py` (referencial formal, perfis `human_adult`/`stylized`), `rig.py` (Unity, Mixamo, com calibração e marcação `calibrated`), heurísticas anatômicas como avisos |
| **Novo** | **Manequim com sinais invertidos** | **Sim, desde a v0.4** | `skeleton.py` | Flexão de ombro, quadril, cotovelo e joelho iam para trás; abdução cruzava o corpo; inclinação de pescoço/coluna e torção iam para o lado errado | Corrigido; testes de regressão por junta, eixo e `body_yaw`. Só aparecia de perfil ou em torção, por isso passou |
| **Novo** | `deps.delta` perdia asserts ao remover entidade | Sim (introduzido e corrigido nesta missão) | `deps.py` | Grafo novo sobrescrevia as referências do antigo | União dos dois grafos; teste |
| **Novo** | `compact` caía em `unsupported` | Sim (introduzido e corrigido nesta missão) | `loss.py` | Destino sem regra própria | `ALIAS` herda do backend de origem; teste para todos os backends |

### Eficiência

- Validar a cena: ~11 ms; compilar: ~2 ms; medir uma imagem de 1,5 MP: ~1,5 s; `pack` completo: ~0,2 s. O custo está em **medir**, não em validar.
- **Validação incremental não foi feita**: não compensa a 11 ms, e o validador é monolítico por escolha (reporta todos os erros de uma vez). O que existe é a análise de dependências (`deps.delta`) que diz quais asserts e verificadores uma edição afeta.
- Cache em memória por conteúdo para leitura da cena e **medição de imagens**; invalida por mudança de chave.
- Pose: juntas simétricas iguais viram uma frase (no sapo mago, as 4 frases de quadris e joelhos viram 2).
- Perdas: destino por chave e backend, com fidelidade que nunca promete mais do que preserva.
- **Resultado desfavorável, medido**: a SceneLang completa gasta ~3,7× mais tokens de entrada que uma linearização ingênua da mesma cena (1152 × 315 no sapo mago, estimativa por caracteres); a compacta, ~3,0×. A vantagem precisa vir de **menos tentativas e mais restrições cumpridas**, o que só uma avaliação com gerador mede (ver F e E).

## B. Arquivos modificados

Novos: `canon.py`, `correction/{types,rules,history,planner}.py`, `anatomy.py`, `rig.py`, `cache.py`, `patch.py`, `deps.py`, `bench.py`, `mcp_server.py` (v0.6).
Alterados: `correct.py` (reescrito sobre o motor), `pack.py` (guia, manifesto, integridade), `locate.py` (estados), `loss.py` (destinos), `pose.py` (perfis, heurísticas, frase compacta), `skeleton.py` (sinais), `compile.py` (`compact`, `delta_prompt`), `api.py`, `cli.py` (`diff`, `patch`, `delta-prompt`, `bench`, `unpack --check`, `pack --strict`, `pose --export`, `locate` com estados), `pyproject.toml`, `docs/LANGUAGE.md`, `skill/scenelang/SKILL.md`.

## C. Testes

- Criados nesta missão: `test_canon`, `test_correction_engine`, `test_pack_integrity`, `test_locate_states`, `test_loss_fates`, `test_pose_layers`, `test_incremental`, `test_bench`, `test_examples_invariants` (+ `test_mcp`), cerca de 150 casos novos (205 → 352).
- Executados: suíte completa, Python 3.13. **352 aprovados, 2 ignorados, 0 reprovados.**
- Python 3.10 (mínimo declarado): sintaxe conferida em 3.11 (`ast.parse`); a suíte **não** foi executada em 3.10 nem 3.11 (sem dependências instaladas nelas).
- Alguns testes meus falharam por expectativa errada (não por defeito) e foram corrigidos com justificativa; três pegaram defeitos reais no código (sinais do manequim, união de grafos no `deps`, `compact` sem destino).
- Problemas que continuam: ver D.

## D. Comparação arquitetural e limitações

Antes: `correct.py` monolítico (medir + decidir + escrever), `locate` devolvendo caixas ou nada, `pack` sem verificação, perdas em três níveis.
Agora: camadas com contratos (`Finding → Rule → Plan → History → Report`; `Found` com estado; manifesto de pacote; destino por chave), todas extensíveis por registro.

Limitações que permanecem:
- `seg` é retângulo; não há máscara, profundidade nem partes do corpo (só interface reservada).
- `locate` por cor continua frágil; os estados só o tornam **honesto** (ele recusa decidir em vez de errar).
- Conversão de pose para rigs não está calibrada: só nomes de ossos; ângulos seguem na convenção do scenelang.
- O manequim tem proporções humanas (não serve para um sapo).
- Cache só em memória; patches perdem comentários YAML.
- O benchmark não foi executado contra nenhum gerador.
- Perfil `stylized` (+25%) é convenção de estilo, não dado anatômico.
- Os nomes de osso de Unity/Mixamo seguem a documentação pública; confira no seu modelo.

## E. Próximos passos

**Críticas**
1. Rodar o benchmark com um gerador real (≥ 10 cenas, baseline escrito à mão): é a única forma de provar a vantagem, e hoje a entrada custa mais tokens.
2. Medição por visão (modelo olha a imagem e devolve `--boxes`) automatizada: tira o `locate` da dependência de cor.
3. Calibrar um rig de verdade (Blender/Unity) e validar `to_rig` numericamente.

**Importantes**
4. Máscaras reais no `seg` (a partir de `mask` na entidade ou de segmentação por modelo).
5. Proporções de manequim por espécie/`character` (sapo, criança, criatura).
6. Reduzir o prompt completo (hoje 4 KB no sapo mago) medindo qual bloco realmente muda o resultado.
7. Execução em Python 3.10 no CI.

**Futuras**
8. Adaptadores para vídeo/3D (Blender previz), runtime com cache em disco, Universal Visual IR formal.

## F. Avaliação final

1. **Mais confiável?** Sim, de forma mensurável: três defeitos reais achados e corrigidos (manequim com sinais invertidos, hash não canônico, correção falsa por medição fraca) e o sistema agora recusa decidir quando a evidência é fraca.
2. **Mais eficiente?** Em partes: medição em cache, sem reavaliar o que a edição não toca, prompt de edição só com o que mudou, pose compacta. **Em tokens de entrada, não**: o prompt completo é ~3,7× maior que o ingênuo. A eficiência real depende de reduzir tentativas, ainda não medido.
3. **Correção preparada para novas modalidades?** Sim em arquitetura (nova modalidade = novas `Rule` e novo `Finding.kind`, sem mexer no núcleo); não em cobertura: só há regras para o que o `verify`/`locate` medem hoje.
4. **Mais perto de uma infraestrutura universal?** Um passo: há IR compilável para quatro destinos, relatório de perdas por destino, pose em camadas com perfil de rig e interface de guia extensível. Falta o IR canônico formal e adaptadores reais.
5. **Três maiores gargalos:** (a) falta de evidência de que reduz tentativas (benchmark sem gerador); (b) medição de posição sem visão automatizada; (c) o `seg` e o manequim ainda são geometria aproximada (caixas, proporção humana).
