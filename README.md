# Crimson Desert — Map Companion

Sistema de overlay para o mapa do [MapGenie](https://mapgenie.io/crimson-desert) que lê
a posição do jogador em tempo real a partir da memória do processo `CrimsonDesert.exe`
e exibe um marcador ao vivo no mapa interativo.

---

## Arquitetura

```
CrimsonDesert.exe
       │  (pymem — leitura de memória via code caves / hooks)
       ▼
CD_Companion.exe  (processo único, sem console)
  ├── Thread daemon: server/main.py   ← servidor WebSocket em background
  │     ws://0.0.0.0:7891
  │
  └── Main thread: overlay/main.py    ← única janela visível (PyQt5)
        └── QWebEngineView → mapgenie.io + inject.js
```

---

## Pré-requisitos

```
pip install pymem websockets PyQt5 PyQtWebEngine
```

Python **≥ 3.10**.

---

## Como usar

### Modo fácil — Executável compilado

Execute `CD_Companion.exe` (ou `python launcher.py`).

O executável:
1. Pede elevação UAC automaticamente
2. Inicia o servidor WebSocket como thread daemon
3. Abre o overlay PyQt5 — **uma única janela, sem consoles extras**
4. Logs vão para `cd_server.log` no diretório do executável

### Modo manual (desenvolvimento)

```bat
:: Overlay + servidor embutido (janela única)
python -m overlay.main

:: Ou servidor standalone (para debug)
python -m server.main
```

### Compilar o executável

```bat
scripts\build_launcher.bat
```

Gera `dist\CD_Companion.exe` com `--noconsole` (sem janela de console).

---

## Interface

### Janela principal (overlay)

| Elemento | Descrição |
|---|---|
| Hover no topo | Exibe a barra de controles (modo normal) ou botões flutuantes (modo circular) |
| `◀` | Voltar (histórico do WebView) |
| `⚙` | Configurações |
| `–` | Minimizar (mesmo efeito que Ctrl+Shift+M) |
| `✕` | Fechar e salvar posição/tamanho |
| Redimensionar | Qualquer borda ou canto da janela |
| **Ctrl + arrastar** | Mover a janela arrastando em qualquer área |

**Atalho global:** `Ctrl+Shift+M` — mostrar / ocultar a janela

### Botão Follow (canto inferior direito do mapa)

| Ação | Efeito |
|---|---|
| Click | Ativa / desativa "seguir jogador" |
| `⊞` (ao lado) | Abre painel completo (coordenadas, status, teleport) |
| Segurar **Shift** | Pausa o follow temporariamente |

### Painel de status

- Coordenadas em tempo real: X, Z, Y + Realm (Pywel / Abyss)
- **📍 Ir ao Marcador** — teleporta para o marcador colocado no mapa in-game
- **↩ Abortar** — retorna à posição anterior ao último teleport
- **🎯 Calibração** — modo de calibração

### Painel de Waypoints (canto inferior esquerdo, botão ⭕)

- **+ Salvar** — salva posição atual com nome
- **⭕** — teleporta para o waypoint
- **✕** — remove waypoint
- Filtro por texto

### Teleport pelo centro da tela (botão ◎)

- Slider de altura Y
- Teleporta para as coordenadas do centro visível do mapa

---

## Teleport

Todos os teleports aplicam automaticamente:
- **HEIGHT_BOOST +10 unidades** no eixo Y (evita travar no chão)
- **Invulnerabilidade por 10 segundos** após o teleport

Waypoints pessoais ficam em:
```
%LOCALAPPDATA%\CD_Teleport\cd_overlay_waypoints.json
```

---

## Calibração de coordenadas

O sistema converte coordenadas do jogo (X, Z) para lng/lat do MapGenie usando
uma transformação afim calibrada com pontos de referência.

**Calibrações padrão** (Pywel e Abyss) já estão embutidas.

**Para recalibrar:**
1. Abra o painel completo e clique em **🎯 Calibração: OFF** → ativa o modo
2. No jogo, vá até um local reconhecível
3. No mapa (MapGenie), clique exatamente sobre esse local
4. O ponto é salvo em `%LOCALAPPDATA%\CD_Teleport\cd_calibration_pywel.json`
5. Com **≥ 3 pontos**, a calibração afim substitui a linear padrão
6. Para resetar: comando `reset_calibration` via WebSocket

---

## Configurações

Acessíveis pelo botão `⚙` na barra (hover no topo da janela):

| Opção | Padrão | Descrição |
|---|---|---|
| Restaurar última posição do mapa | ✅ | Retorna ao local e zoom da última visita |
| Ocultar Locais Encontrados | ✅ | Desativa "Found Locations" automaticamente |
| Ocultar Painel Esquerdo | ☐ | Fecha o sidebar esquerdo ao carregar |
| Ocultar Painel Direito | ☐ | Fecha o sidebar direito ao carregar |
| Janela circular/oval | ☐ | Aplica máscara elíptica; redimensiona para 240×240 |
| Seguir janela do jogo | ☐ | Move o overlay junto com a janela do jogo |
| Transparência | 0% | Opacidade da janela (0% a 90%) |
| Seta de direção | Auto | `Auto` / `Entity vector` / `Delta posição` |
| Girar mapa com player | ☐ | Bearing do mapa segue o heading do jogador |
| Girar mapa com câmera | ☐ | Bearing do mapa segue a câmera do jogo |

Salvas em `overlay_config.json` (diretório do executável ou do script).

---

## Hotkeys globais

| Hotkey | Ação |
|---|---|
| `Ctrl+Shift+M` | Mostrar / ocultar overlay |
| `F5` | Teleportar para marcador do mapa in-game |
| `Shift+F5` | Abortar (voltar à posição pré-teleport) |

Hotkeys configuráveis em `%LOCALAPPDATA%\CD_Teleport\cd_hotkeys.json`.

---

## WebSocket — Protocolo

### Servidor → Clientes

```json
{ "type": "position", "lng": -0.72, "lat": 0.61,
  "x": -8432.1, "y": 12.4, "z": 3201.7, "realm": "pywel",
  "heading": 45.2 }
```

```json
{ "type": "camera_heading", "heading": 33.7, "raw": 0.5882 }
```

```json
{ "type": "waypoints", "data": [ { "name": "...", "absX": 0, "absY": 0, "absZ": 0, "realm": "pywel" } ] }
```

```json
{ "type": "engine_status", "status": "attached" }
```

```json
{ "type": "location_toggle", "locationId": "549771", "found": true }
```

### Clientes → Servidor

| `cmd` | Parâmetros | Efeito |
|---|---|---|
| `teleport` | `x, y, z` | Teleporta para coordenadas absolutas |
| `teleport_map` | `lng, lat, y, realm` | Teleporta para ponto clicado no mapa |
| `teleport_marker` | — | Teleporta para marcador do mapa in-game |
| `abort` | — | Retorna à posição pré-teleport |
| `move` | `dx, dy, dz` | Injeta delta de posição via physics hook |
| `save_waypoint` | `name` | Salva posição atual |
| `delete_waypoint` | `index` | Remove waypoint pelo índice |
| `rename_waypoint` | `index, name` | Renomeia waypoint |
| `add_calibration` | `lng, lat, realm` | Adiciona ponto de calibração |
| `reset_calibration` | `realm` | Remove calibração salva |
| `location_toggle` | `locationId, found` | Propaga marcação para outros clientes |

---

## Sync de marcações entre clientes

Quando qualquer cliente marca ou desmarca uma location no MapGenie, a mudança é
propagada automaticamente para todos os outros clientes conectados.

1. O JS intercepta `fetch`/`XMLHttpRequest` para detectar PUT/DELETE em `/api/v1/user/locations/{id}`
2. Envia `location_toggle` ao servidor
3. O servidor faz broadcast para os demais clientes
4. Cada cliente chama `window.mapManager.markLocationAsFound(id, found)` para atualizar visualmente

---

## Estrutura de arquivos

```
├── launcher.py              # Entry point — elevação UAC + chama overlay.main
├── server/
│   ├── main.py              # Servidor WebSocket + broadcast de posição
│   └── memory/engine.py     # TeleportEngine: attach, AOB scan, hooks, teleport
├── overlay/
│   ├── main.py              # OverlayWindow + servidor como thread daemon
│   ├── inject.js            # JS injetado no MapGenie (Template com $WS_URL)
│   ├── widgets.py           # SettingsDialog, TitleBar, InterceptPage, LoginPrompt
│   └── config_defaults.py   # SETTING_DEFAULTS
├── shared/
│   └── coord_math.py        # Funções puras: calibração, conversão, heading
├── tests/
│   └── test_coords.py       # Testes unitários (shared.coord_math)
└── scripts/
    ├── build_launcher.bat   # Compila launcher.py → dist/CD_Companion.exe
    ├── gen_cert.py          # Gera certificado SSL para WSS
    └── gen_icon.py          # Gera ícone do launcher
```

---

## Como o hook de memória funciona

1. **AOB Scan**: busca padrões de bytes no módulo `CrimsonDesert.exe`
2. **Code Cave**: aloca memória e escreve assembly que captura XYZ
3. **JMP Patch**: substitui a instrução original por um `JMP` para o cave (trampoline)
4. **Leitura**: o servidor lê os floats XYZ do bloco alocado a cada ~16 ms (60 Hz)
5. **Mundo**: coordenadas locais + world offset = posição absoluta

Baseado no projeto [CDTT (dencoexe)](https://github.com/dencoexe/CDTT).

---

## Licença

Este projeto é disponibilizado para fins educacionais. Use por sua conta e risco.
