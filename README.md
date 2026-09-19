# Horários Família 2026–2027

Aplicação PWA para consulta integrada dos horários familiares e da informação diária relevante.

## Funcionalidades

- vista **Hoje**, vista de conjunto e horários individuais;
- navegação por data otimizada para toque, contagens do calendário escolar e interrupções;
- efemérides, História mundial e História de Portugal;
- astronomia, liturgia, santos do dia e Evangelho;
- integração do **Passo-a-Rezar** através de leitor de áudio direto, sem incorporar a página externa, evitando banners de cookies e promoção da app;
- agenda desportiva apresentada apenas nas datas com eventos;
- resultados/estado de jogos acompanhados e ligações específicas quando disponíveis;
- instalação como PWA e funcionamento offline com service worker;
- atualização automática dos dados através de GitHub Actions.

## Estrutura dos dados

- `calendar-info.json` / `daily-info.json` — calendário, liturgia e informação diária;
- `history-info.json` — efemérides históricas;
- `sports-info.json` — agenda e resultados desportivos;
- `scripts/` — atualização e validação das fontes;
- `.github/workflows/` — automatizações de atualização.

A interface principal está em `index.html`; `sw.js` gere atualização e cache offline.
