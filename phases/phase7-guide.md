# Fase 7 — Experiencia moderna: animaciones, UI, imágenes

**Objetivo:** Hacer el bot visualmente atractivo — imágenes generadas con Pillow, animaciones en vivo, botones estilizados, formato HTML rico, spoilers y stickers.

---

## Estado Actual

| Componente | Estado |
|---|---|
| `Pillow` / `matplotlib` | En `requirements.txt` pero `Pillow` no instalado |
| Lobby: animación de puntos | ✅ Ya existe (`_animation_loop` cada 5s) |
| Countdown de ronda | ❌ No existe — solo `asyncio.sleep(round_time)` |
| Imágenes de letra de ronda | ❌ No existe |
| Imagen de podio final | ❌ No existe |
| Cartas de logros | ❌ No existen |
| Tabla semanal como imagen | ❌ No existe |
| Spoiler en respuestas | ❌ No existe |
| Stickers temporales | ❌ No existe |
| Formato HTML en mensajes | ✅ Parcial (algunos usan `hbold`, otros raw HTML) |
| Barras de progreso con emojis | ❌ No existen |
| Paginación en teclado letras | ❌ 6 por fila, sin paginación real |
| `/start` con imagen | ❌ Solo texto |
| `/help` con imagen | ❌ Solo texto |
| `/profile` con gráfico | ❌ Solo texto |
| `/stats` con gráfico semanal | ❌ Solo texto |

---

## Dependencias Nuevas

Instalar antes de empezar:

```powershell
cd backend
pip install "pillow>=11.0,<12.0" "matplotlib>=3.0,<4.0"
```

`pillow` se usa para **generar imágenes** (letra de ronda, podio, logros, leaderboard).
`matplotlib` se usa para **gráficos de estadísticas** (actividad semanal en `/stats`).

---

## Vista General de Cambios

```
backend/
├── requirements/requirements.txt   # pillow ya está, matplotlib ya está
├── assets/                          # NUEVA carpeta para fuentes/imágenes base
│   ├── fonts/
│   │   └── Montserrat-Bold.ttf     # Fuente moderna (descargar gratis de Google Fonts)
│   └── backgrounds/
│       ├── round_bg.png            # Fondo degradado para letra de ronda
│       └── podium_bg.png           # Fondo para podio
├── src/
│   ├── services/
│   │   ├── round_manager.py         # MODIFICAR — countdown animado + spoilers
│   │   └── game_orchestrator.py     # MODIFICAR — countdown inicio 3-2-1
│   ├── image_generator.py          # NUEVO — todas las funciones de imágenes
│   ├── keyboards/
│   │   ├── round.py                # MODIFICAR — paginación letras (2 filas de 13)
│   │   └── lobby.py                # MODIFICAR — emojis más visibles
│   ├── handlers/
│   │   ├── start.py                # MODIFICAR — +imagen de bienvenida
│   │   ├── game/
│   │   │   ├── profile.py          # MODIFICAR — +gráfico de progreso XP
│   │   │   ├── stats.py            # MODIFICAR — +gráfico semanal
│   │   │   ├── leaderboard.py      # MODIFICAR — +imagen de tabla semanal
│   │   │   └── lobby.py            # MODIFICAR — +countdown inicio visible
│   │   └── group.py                # MODIFICAR — +imagen al agregar bot
│   └── i18n.py                     # MODIFICAR — textos para nuevas funciones
└── tests/
    └── test_image_generator.py     # NUEVO — tests de generación de imágenes
```

---

## Tarea 7.1 — Mensajes animados (countdown + lobby mejorado)

### 7.1.1 Countdown en inicio de ronda (3-2-1)

**Archivo:** `backend/src/services/game_orchestrator.py`

En `_do_start`, justo antes de llamar a `round_manager.start_round`, añadir un countdown visible de 3 segundos:

```python
async def _do_start(self, state: LobbyState, bot: Bot) -> None:
    # ... (código existente hasta el envio de "Partida iniciada!")

    await bot.send_message(
        state.group_chat_id,
        f"🎮 <b>¡Partida iniciada!</b>\n\n"
        f"{len(state.player_telegram_ids)} jugadores:\n"
        f"{participants}",
    )

    # --- NUEVO: COUNTDOWN 3-2-1 ---
    count_msg = await bot.send_message(
        state.group_chat_id,
        "⏰ <b>Preparando ronda 1...</b>",
    )
    for i in range(3, 0, -1):
        await asyncio.sleep(1)
        try:
            await count_msg.edit_text(
                f"<b>{i}...</b>",
            )
        except TelegramBadRequest:
            pass
    try:
        await count_msg.delete()
    except TelegramBadRequest:
        pass
    # --- FIN COUNTDOWN ---

    # ... (resto del código: crear round)
```

### 7.1.2 Countdown animado durante la ronda

**Archivo:** `backend/src/services/round_manager.py`

Reemplazar `_round_timer` (línea ~1003) con una versión que edita el mensaje cada segundo:

```python
async def _round_timer(self, state: RoundState, bot: Bot) -> None:
    try:
        for remaining in range(state.round_time, 0, -1):
            if state.timer_task and state.timer_task.done():
                return
            try:
                text = self._format_round_message(
                    state.round_number, state.letter,
                    state.categories, remaining
                )
                # Añadir seccion de respondidos
                parts = [text]
                if state.submitted_player_ids:
                    parts.append("")
                    parts.append("✅ <b>Respondieron:</b>")
                    for pid in state.submitted_player_ids:
                        name = state.player_names.get(pid, f"Jugador {pid}")
                        completed = "⭐" if pid in state.complete_player_ids else "⬜"
                        parts.append(f"  {completed} {name}")
                if state.first_completer_id:
                    name = state.first_completer_name or "Alguien"
                    parts.append("")
                    parts.append(f"⏹ <b>{name} completó todas las categorías</b>")
                    parts.append(f"  Stop: {state.stop_presses}/{NUM_STOP_BUTTONS}")
                await bot.edit_message_text(
                    "\n".join(parts),
                    chat_id=state.message_chat_id,
                    message_id=state.message_id,
                )
            except TelegramBadRequest:
                pass
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)

            # Esperar 1s pero permitir cancelación
            try:
                await asyncio.wait_for(
                    asyncio.get_event_loop().create_future(), timeout=1
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return

        # Tiempo agotado
        async with self._lock_for(state.game_id):
            await self._close_round(state.game_id, "timeout", bot)

    except asyncio.CancelledError:
        pass
```

> ⚠️ **Nota:** El loop de 1s reemplaza el `asyncio.sleep(state.round_time)` actual. Asegúrate de **no** duplicar el timer. Comenta o elimina la llamada antigua a `_round_timer` desde `start_round`.

### 7.1.3 Lobby: animación mejorada

**Archivo:** `backend/src/services/game_orchestrator.py`

El `_animation_loop` actual ya hace puntos suspensivos cada 5s. Mejorarlo:

```python
# En _animation_loop, cambiar el conjunto de animaciones:
frames = ["🛑 STOP - Sala abierta", "🛑 STOP - Sala abierta .", 
          "🛑 STOP - Sala abierta ..", "🛑 STOP - Sala abierta ...",
          "🛑 STOP - Sala abierta"]
# En lugar de solo puntos, alternar entre estados
```

No requiere cambio de código significativo — el patrón actual ya funciona. Solo asegúrate de que el intervalo sea de 3s en vez de 5s para que se sienta más vivo:

```python
# Línea 314: cambiar
await asyncio.sleep(5)
# → 
await asyncio.sleep(3)
```

---

## Tarea 7.2 — Imágenes generadas con Pillow

### 7.2.1 Estructura de assets

Crear carpeta `backend/assets/` con:

```
assets/
├── fonts/
│   └── Montserrat-Bold.ttf    # Descargar de Google Fonts
└── backgrounds/
    ├── round_bg.png            # 512x512, degradado azul-morado
    └── podium_bg.png           # 800x600, fondo oscuro elegante
```

**Cómo generar los backgrounds con Pillow (script único `assets/generate_backgrounds.py`):**

```python
"""Genera los backgrounds base para las imágenes del bot."""
from PIL import Image, ImageDraw
import math

def make_gradient(w, h, color1, color2):
    img = Image.new("RGBA", (w, h))
    for y in range(h):
        ratio = y / h
        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
        for x in range(w):
            img.putpixel((x, y), (r, g, b, 255))
    return img

# Round bg: 512x512 degradado azul marino → violeta
round_bg = make_gradient(512, 512, (30, 60, 120), (80, 30, 100))
round_bg.save("assets/backgrounds/round_bg.png")

# Podium bg: 800x600 degradado oscuro
podium_bg = make_gradient(800, 600, (20, 20, 40), (10, 10, 20))
podium_bg.save("assets/backgrounds/podium_bg.png")

print("Backgrounds generados en assets/backgrounds/")
```

### 7.2.2 Generador central de imágenes

**Archivo NUEVO:** `backend/src/image_generator.py`

```python
import logging
import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
_BG_DIR = os.path.join(_ASSETS_DIR, "backgrounds")
_FONT_DIR = os.path.join(_ASSETS_DIR, "fonts")

# Colores y constantes
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
GOLD = (255, 215, 0, 255)
SILVER = (192, 192, 192, 255)
BRONZE = (205, 127, 50, 255)


def _get_font(size: int = 40) -> ImageFont.FreeTypeFont:
    """Carga la fuente Montserrat Bold. Fallback a default si no existe."""
    font_path = os.path.join(_FONT_DIR, "Montserrat-Bold.ttf")
    try:
        return ImageFont.truetype(font_path, size)
    except (IOError, OSError):
        logger.warning("Fuente Montserrat no encontrada en %s, usando default", font_path)
        return ImageFont.load_default()


def _load_bg(name: str, size: tuple[int, int]) -> Image.Image:
    """Carga un background o crea uno sólido si no existe."""
    path = os.path.join(_BG_DIR, name)
    try:
        img = Image.open(path).resize(size, Image.LANCZOS)
        return img.convert("RGBA")
    except (IOError, OSError):
        logger.warning("Background %s no encontrado, usando sólido", path)
        img = Image.new("RGBA", size, (30, 30, 60, 255))
        return img


def _center_text(draw: ImageDraw, text: str, font: ImageFont, y: int, color=WHITE) -> None:
    """Dibuja texto centrado horizontalmente."""
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (draw.im.size[0] - w) // 2
    draw.text((x, y), text, font=font, fill=color)


# ─── 7.2.3 Imagen de letra de ronda ─────────────────────────────────────

def generate_round_letter_image(
    letter: str,
    round_number: int,
    category_count: int = 8,
) -> Optional[bytes]:
    """
    Genera una imagen PNG 512x512 con la letra de la ronda grande al centro,
    fondo degradado, número de ronda arriba.

    Returns:
        bytes de la imagen PNG, o None si falla.
    """
    try:
        img = _load_bg("round_bg.png", (512, 512))
        draw = ImageDraw.Draw(img)

        # Número de ronda arriba
        font_small = _get_font(36)
        _center_text(draw, f"RONDA {round_number}", font_small, 60, (200, 200, 255, 255))

        # Letra gigante al centro
        font_big = _get_font(200)
        _center_text(draw, letter.upper(), font_big, 150, WHITE)

        # Categorías abajo
        font_cat = _get_font(24)
        _center_text(draw, f"{category_count} categorías", font_cat, 420, (180, 180, 200, 255))

        buf = bytearray()
        img.save(buf, format="PNG")
        return bytes(buf)
    except Exception as e:
        logger.exception("Error generando imagen de letra: %s", e)
        return None


# ─── 7.2.4 Imagen de podio final ──────────────────────────────────────────

def generate_podium_image(
    winners: list[tuple[str, int]],  # [(name, score), ...]
    game_rounds: int = 5,
) -> Optional[bytes]:
    """
    Genera una imagen 800x600 con el podio final.

    Args:
        winners: lista de (nombre, puntaje), ordenados del 1ro al último.
        game_rounds: rondas totales que tuvo la partida.
    """
    try:
        img = _load_bg("podium_bg.png", (800, 600))
        draw = ImageDraw.Draw(img)

        # Título
        font_title = _get_font(48)
        _center_text(draw, "🏆 PODIO FINAL", font_title, 30, GOLD)

        # Subtítulo
        font_sub = _get_font(24)
        _center_text(draw, f"{game_rounds} rondas jugadas", font_sub, 85, (200, 200, 200, 255))

        # Si no hay ganadores
        if not winners:
            _center_text(draw, "Sin puntuaciones", _get_font(36), 280, (255, 100, 100, 255))
            buf = bytearray()
            img.save(buf, format="PNG")
            return bytes(buf)

        # Dibujar top 3
        medals = ["🥇", "🥈", "🥉"]
        medal_colors = [GOLD, SILVER, BRONZE]
        font_name = _get_font(36)
        font_score = _get_font(28)

        start_y = 160
        for i, (name, score) in enumerate(winners[:3]):
            y = start_y + i * 120

            # Medalla
            font_medal = _get_font(48)
            _center_text(draw, medals[i], font_medal, y, medal_colors[i])

            # Nombre
            _center_text(draw, name, font_name, y + 55, WHITE)

            # Puntaje
            _center_text(draw, f"{score} pts", font_score, y + 90, medal_colors[i])

        # Si hay más de 3 jugadores, listar el resto más abajo
        if len(winners) > 3:
            font_rest = _get_font(22)
            rest_text = " | ".join(
                f"{i+1}. {n}: {s}pts"
                for i, (n, s) in enumerate(winners[3:])
            )
            _center_text(draw, rest_text, font_rest, 530, (150, 150, 150, 255))

        buf = bytearray()
        img.save(buf, format="PNG")
        return bytes(buf)
    except Exception as e:
        logger.exception("Error generando imagen de podio: %s", e)
        return None


# ─── 7.2.5 Imagen de leaderboard semanal ───────────────────────────────────

def generate_leaderboard_image(
    entries: list[tuple[int, str, int]],  # [(rank, name, score), ...]
    week_label: str = "Esta semana",
) -> Optional[bytes]:
    """
    Genera una imagen 600x800 con la tabla del leaderboard semanal.
    """
    try:
        img = Image.new("RGBA", (600, 800), (20, 20, 40, 255))
        draw = ImageDraw.Draw(img)

        font_title = _get_font(40)
        _center_text(draw, "📊 TOP SEMANAL", font_title, 30, GOLD)

        font_sub = _get_font(22)
        _center_text(draw, week_label, font_sub, 75, (200, 200, 200, 255))

        if not entries:
            _center_text(draw, "Sin datos aún", _get_font(32), 380, (255, 100, 100, 255))
            buf = bytearray()
            img.save(buf, format="PNG")
            return bytes(buf)

        font_entry = _get_font(28)
        font_score = _get_font(24)
        medals_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}

        y = 130
        for rank, name, score in entries[:10]:
            prefix = medals_emoji.get(rank, f"{rank}.")
            display = f"{prefix} {name}"
            bbox = draw.textbbox((0, 0), display, font=font_entry)
            text_w = bbox[2] - bbox[0]
            x = (600 - text_w) // 2
            draw.text((x, y), display, font=font_entry, fill=WHITE)

            # Score a la derecha
            score_text = f"{score} pts"
            bbox2 = draw.textbbox((0, 0), score_text, font=font_score)
            score_x = 600 - (bbox2[2] - bbox2[0]) - 30
            draw.text((score_x, y + 5), score_text, font=font_score, fill=GOLD)

            y += 60

        buf = bytearray()
        img.save(buf, format="PNG")
        return bytes(buf)
    except Exception as e:
        logger.exception("Error generando leaderboard image: %s", e)
        return None


# ─── 7.2.6 Carta de logro ──────────────────────────────────────────────────

def generate_achievement_card(
    title: str,
    description: str,
    emoji: str = "🏆",
    color: tuple = (255, 215, 0),
) -> Optional[bytes]:
    """
    Genera una imagen 400x200 tipo "logro desbloqueado".
    """
    try:
        img = Image.new("RGBA", (400, 200), (25, 25, 50, 255))
        draw = ImageDraw.Draw(img)

        # Borde dorado
        draw.rectangle([5, 5, 395, 195], outline=color, width=3)

        # Emoji grande
        font_emoji = _get_font(64)
        _center_text(draw, emoji, font_emoji, 15)

        # Título
        font_title = _get_font(32)
        _center_text(draw, title, font_title, 85, WHITE)

        # Descripción
        font_desc = _get_font(20)
        _center_text(draw, description, font_desc, 125, (180, 180, 200, 255))

        # "LOGRO DESBLOQUEADO"
        font_tag = _get_font(16)
        _center_text(draw, "🏅 LOGRO DESBLOQUEADO", font_tag, 165, color)

        buf = bytearray()
        img.save(buf, format="PNG")
        return bytes(buf)
    except Exception as e:
        logger.exception("Error generando achievement card: %s", e)
        return None
```

### 7.2.7 Integrar imágenes en el flujo del juego

**Archivo:** `backend/src/services/round_manager.py`

**Para enviar la imagen de letra al inicio de cada ronda:**

En `start_round`, después de crear el mensaje de ronda, enviar la imagen:

```python
# En start_round, justo después de enviar el mensaje de ronda:
from src.image_generator import generate_round_letter_image

img_bytes = generate_round_letter_image(
    letter=letter,
    round_number=round_number,
    category_count=len(categories) if categories else 8,
)
if img_bytes:
    from io import BytesIO
    from aiogram.types import BufferedInputFile

    photo = BufferedInputFile(img_bytes, filename=f"round_{round_number}.png")
    await bot.send_photo(
        chat_id=group_chat_id,
        photo=photo,
        caption=f"🛑 <b>Ronda {round_number} — Letra: {letter}</b>",
    )
```

Luego **quitar** la primera línea del mensaje de texto (`f"🛑 <b>Ronda {round_number} — Letra: {letter}</b>\n"`) para no duplicar la info, ya que la imagen la muestra.

**Para enviar la imagen de podio al final:**

En `_end_game`, reemplazar el podio de texto con una imagen:

```python
# En _end_game, donde se construye el podio:
from src.image_generator import generate_podium_image

podium_data = [(name, score) for pid, score in winners[:5]]
podium_bytes = generate_podium_image(podium_data, state.total_rounds)
if podium_bytes:
    from io import BytesIO
    from aiogram.types import BufferedInputFile

    photo = BufferedInputFile(podium_bytes, filename="podium.png")
    # Enviar imagen de podio
    await bot.send_photo(state.group_chat_id, photo=photo)
else:
    # Fallback: enviar texto como antes
    ...
```

---

## Tarea 7.3 — Botones inline mejorados

### 7.3.1 Paginación en teclado de letras

**Archivo:** `backend/src/keyboards/round.py`

Reemplazar `letter_keyboard` con 2 filas de 13 (en lugar de 6 por fila):

```python
def letter_keyboard(game_id: int, include_n: bool = False) -> InlineKeyboardMarkup:
    letters = list(LETTERS)
    if include_n:
        idx = letters.index("N") + 1
        letters.insert(idx, "Ñ")

    # Dividir en 2 filas: primeras 13, segundas 13-14
    mid = (len(letters) + 1) // 2
    row1 = letters[:mid]
    row2 = letters[mid:]

    keyboard = [
        [
            InlineKeyboardButton(
                text=f"🔤 {letter}",
                callback_data=f"letter:{game_id}:{letter}",
            )
            for letter in row1
        ],
        [
            InlineKeyboardButton(
                text=f"🔤 {letter}",
                callback_data=f"letter:{game_id}:{letter}",
            )
            for letter in row2
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
```

### 7.3.2 Botón Stop con emoji de escudo

**Archivo:** `backend/src/keyboards/round.py`

En `stop_keyboard`, usar emoji de escudo y la barra de progreso:

```python
def stop_keyboard(game_id: int, stop_number: int) -> InlineKeyboardMarkup:
    filled = "🟩" * stop_number
    empty = "⬜" * (10 - stop_number)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🛑 Stop {filled}{empty}",
                    callback_data=f"stop:{game_id}:{stop_number}",
                )
            ]
        ]
    )
```

### 7.3.3 Botón de lobby más descriptivo

**Archivo:** `backend/src/keyboards/lobby.py`

```python
def lobby_keyboard(game_id: int, is_host: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text="🟢 Unirse a la partida",
            callback_data=f"join:{game_id}"
        )]
    ]
    if is_host:
        buttons.append(
            [InlineKeyboardButton(
                text="▶️ Iniciar partida ahora",
                callback_data=f"start:{game_id}"
            )]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

---

## Tarea 7.4 — Efectos visuales

### 7.4.1 Spoiler en respuestas hasta el Stop

**Archivo:** `backend/src/services/round_manager.py`

En `_format_round_message` y en `_do_update_round_message`, cuando la ronda está activa y las respuestas se muestran, usar `<tg-spoiler>` para ocultarlas:

```python
# En _do_update_round_message, donde se enumeran los respondedores,
# NO revelar las respuestas. Solo mostrar nombres.
# Cuando la ronda se cierra (en el resumen), ahí sí mostrar todo.
```

**Cómo implementarlo:**

1. En el mensaje de ronda activa, solo mostrar `✅ Nombre` sin las respuestas.
2. Al cerrar la ronda (`_close_round`), en `_build_summary` mostrar las respuestas de cada jugador envueltas en `<tg-spoiler>`:

```python
# En _build_summary, para cada jugador:
lines.append(f"  {name}: <tg-spoiler>{respuesta}</tg-spoiler>")
```

Esto requiere pasar más datos al `_build_summary` (las respuestas de cada jugador). Puedes obtenerlas desde `_persist_round_scores` (que ya tiene `details`).

### 7.4.2 Stickers temporales

Opcional — requiere crear stickers en @BotFather. El bot puede enviar un sticker al iniciar/terminar una partida:

```python
# Ejemplo de envío de sticker:
# await bot.send_sticker(chat_id, sticker_file_id)
# Los sticker_file_id se obtienen subiendo stickers a @BotFather
```

**Almacenar IDs en `src/core/config.py`:**

```python
class Settings(BaseSettings):
    # ... existing fields ...
    
    # Stickers (opcional, IDs de @BotFather)
    sticker_win: str = ""
    sticker_lose: str = ""
    sticker_achievement: str = ""
```

---

## Tarea 7.5 — Formato de mensajes HTML

### 7.5.1 Barras de progreso con emojis

Crear helper en `backend/src/utils.py`:

```python
def progress_bar(current: int, total: int, length: int = 10) -> str:
    """Genera una barra de progreso con 🟩 y ⬜."""
    filled = int(current / total * length) if total > 0 else 0
    filled = min(filled, length)
    return "🟩" * filled + "⬜" * (length - filled)
```

### 7.5.2 Tablas de puntuación

Crear helper en `backend/src/utils.py`:

```python
def format_score_table(
    scores: list[tuple[str, int]],  # [(name, score), ...]
    title: str = "Puntuaciones",
) -> str:
    """Formatea una tabla de puntuaciones con emojis y HTML."""
    lines = [f"<b>📊 {title}</b>", ""]
    for i, (name, score) in enumerate(scores):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
        bar = progress_bar(score, max(s[1] for s in scores) if scores else 1)
        lines.append(f"{medal} <b>{name}</b>  {bar}")
        lines.append(f"     {score} pts")
        lines.append("")
    return "\n".join(lines)
```

### 7.5.3 Aplicar HTML consistente en todos los mensajes (lista de verificación)

Revisar estos archivos y asegurar que usan HTML con `<b>`, `<i>`, `<code>`, `<tg-spoiler>`:

- [ ] `handlers/start.py` — `/start` y `/help`
- [ ] `handlers/game/lobby.py` — mensajes de lobby, cancel, etc.
- [ ] `handlers/game/round.py` — mensajes de ronda
- [ ] `handlers/game/profile.py` — perfil de jugador
- [ ] `handlers/game/stats.py` — estadísticas
- [ ] `handlers/game/leaderboard.py` — leaderboard
- [ ] `handlers/game/settings.py` — configuración
- [ ] `services/round_manager.py` — `_format_round_message`, `_build_summary`, `_end_game`

El bot ya usa `ParseMode.HTML` por defecto (en `bot.py` línea 156: `default=DefaultBotProperties(parse_mode=ParseMode.HTML)`). Solo debes usar etiquetas HTML en los textos.

---

## Tarea 7.6 — Formato de comandos con imágenes

### 7.6.1 `/start` con imagen de bienvenida

**Archivo:** `backend/src/handlers/start.py`

```python
@start_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    from src.image_generator import generate_round_letter_image
    from io import BytesIO
    from aiogram.types import BufferedInputFile

    img_bytes = generate_round_letter_image("S", 0, 0)
    if img_bytes:
        photo = BufferedInputFile(img_bytes, filename="welcome.png")
        await message.answer_photo(
            photo=photo,
            caption=(
                "<b>🛑 Stop Bot</b>\n\n"
                "El juego clásico de <b>Stop / Basta</b> ahora en Telegram.\n\n"
                "<b>Comandos:</b>\n"
                "• /stop — Iniciar partida\n"
                "• /cancel — Cancelar\n"
                "• /help — Reglas\n"
                "• /profile — Tu perfil\n"
                "• /stats — Estadísticas del grupo\n"
                "• /leaderboard — Top semanal\n"
                "• /rank — Tu puesto semanal\n"
                "• /settings — Configurar (admin)\n\n"
                "¡Añádeme a un grupo y juega con tus amigos!"
            ),
        )
    else:
        # Fallback a solo texto
        # ... (código actual)
```

### 7.6.2 `/profile` con barra de progreso XP

**Archivo:** `backend/src/handlers/game/profile.py`

Ya existe la barra de progreso con `▓` y `░`. Mejorarla con emojis:

```python
# Reemplazar la barra actual (línea ~112):
bar_len = 10
filled = int(xp_data["progress_pct"] / 100 * bar_len)
bar = "🟩" * filled + "⬜" * (bar_len - filled)
lines.append(f"  {bar}  {xp_data['progress_pct']:.0f}%")
```

### 7.6.3 `/stats` con gráfico de actividad semanal

**Archivo:** `backend/src/handlers/game/stats.py`

Añadir generación de gráfico con matplotlib:

```python
# Después de obtener los datos:
from src.image_generator import generate_activity_chart  # ver abajo

chart_bytes = generate_activity_chart(daily_counts)  # daily_counts = [(day_name, count), ...]
if chart_bytes:
    from aiogram.types import BufferedInputFile
    photo = BufferedInputFile(chart_bytes, filename="activity.png")
    await bot.send_photo(chat_id=message.chat.id, photo=photo)
```

**Función `generate_activity_chart` en `image_generator.py`:**

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from io import BytesIO
import os

def generate_activity_chart(daily_data: list[tuple[str, int]]) -> Optional[bytes]:
    """
    Genera un gráfico de barras con la actividad de los últimos 7 días.
    
    Args:
        daily_data: [(nombre_dia, partidas), ...]
    """
    try:
        # Intentar usar fuente con soporte de español
        font_path = os.path.join(_FONT_DIR, "Montserrat-Bold.ttf")
        if os.path.exists(font_path):
            fm.fontManager.addfont(font_path)
            plt.rcParams["font.family"] = fm.FontProperties(fname=font_path).get_name()
        plt.rcParams["font.size"] = 12

        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor("#1a1a2e")
        ax.set_facecolor("#16213e")

        days = [d[0] for d in daily_data]
        counts = [d[1] for d in daily_data]

        bars = ax.bar(days, counts, color="#e94560", edgecolor="#0f3460", linewidth=2)
        ax.set_title("📅 Actividad (7 días)", color="white", fontsize=16, pad=15)
        ax.set_ylabel("Partidas", color="white")
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("#555")
        ax.spines["left"].set_color("#555")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, height,
                        str(int(height)), ha="center", va="bottom", color="white")

        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.exception("Error generando activity chart: %s", e)
        return None
```

**Datos necesarios:** Modificar la query en `/stats` para obtener partidas por día:

```python
# En stats.py, después de la query de recent_games:
from sqlalchemy import cast, Date

daily_stmt = (
    select(
        cast(Game.finished_at, Date).label("day"),
        func.count(Game.id),
    )
    .where(Game.group_chat_id == group_chat_id)
    .where(Game.status == "finished")
    .where(Game.finished_at >= week_ago)
    .group_by(cast(Game.finished_at, Date))
    .order_by(cast(Game.finished_at, Date))
)
daily_rows = await session.execute(daily_stmt)
daily_counts = [(row.day.strftime("%a"), row[1]) for row in daily_rows]
```

### 7.6.4 `/leaderboard` con imagen

**Archivo:** `backend/src/handlers/game/leaderboard.py`

En el handler de `/leaderboard`, después de obtener los datos, generar imagen:

```python
from src.image_generator import generate_leaderboard_image
from aiogram.types import BufferedInputFile

entries = [(row.rank, row[0], row.total_score) for row in top_rows]
img_bytes = generate_leaderboard_image(entries)
if img_bytes:
    photo = BufferedInputFile(img_bytes, filename="leaderboard.png")
    await message.answer_photo(photo=photo)
else:
    # Fallback a texto
    ...
```

### 7.6.5 `/rank` con formato mejorado

**Archivo:** `backend/src/handlers/game/leaderboard.py`

El `/rank` ya funciona. Mejorar el formato:

```python
# En lugar de solo texto, añadir barra de progreso:
rank_bar = progress_bar(rank_data["rank"], max_rank_in_group, 10)
text = (
    f"<b>📊 Tu posición semanal</b>\n\n"
    f"Puesto: <b>#{rank_data['rank']}</b>\n"
    f"Puntaje: <b>{rank_data['score']} pts</b>\n"
    f"Partidas: <b>{rank_data['games_played']}</b>\n\n"
    f"{rank_bar}"
)
```

---

## Orden de implementación sugerido

1. **Instalar Pillow** (`pip install pillow`)
2. **Crear `assets/`** y generar backgrounds
3. **Crear `image_generator.py`** con todas las funciones
4. **Tarea 7.3 — Paginación letras** (cambio simple en keyboard)
5. **Tarea 7.5 — Helpers de formato** (`progress_bar`, `format_score_table`)
6. **Tarea 7.1.1 — Countdown 3-2-1** en `_do_start`
7. **Tarea 7.1.2 — Countdown animado** en `_round_timer`
8. **Tarea 7.2.7 — Integrar imagen de letra** en `start_round`
9. **Tarea 7.2.7 — Integrar imagen de podio** en `_end_game`
10. **Tarea 7.4.1 — Spoiler** en respuestas
11. **Tarea 7.6 — Formatear comandos** con imágenes
12. **Ejecutar `pytest -v`** para verificar que nada se rompió
