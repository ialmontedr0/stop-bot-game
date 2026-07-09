import logging
import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
_BG_DIR = os.path.join(_ASSETS_DIR, "backgrounds")
_FONT_DIR = os.path.join(_ASSETS_DIR, "fonts")
_START_DIR = os.path.join(_ASSETS_DIR, "start")
_HELP_DIR = os.path.join(_ASSETS_DIR, "help")
_PLACEHOLDER_PATH = os.path.join(_ASSETS_DIR, "leaderboard", "profile_placeholder.png")

WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
GOLD = (255, 215, 0, 255)
SILVER = (192, 192, 192, 255)
BRONZE = (205, 127, 50, 255)


def _get_font(size: int = 40) -> ImageFont.FreeTypeFont:
    font_path = os.path.join(_FONT_DIR, "Montserrat-Bold.ttf")
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        logger.warning("Fuente Montserrat no encontrada en %s, usando default", font_path)
        return ImageFont.load_default()


def _load_bg(name: str, size: tuple[int, int]) -> Image.Image:
    path = os.path.join(_BG_DIR, name)
    try:
        img = Image.open(path).resize(size, Image.LANCZOS)
        return img.convert("RGBA")
    except OSError:
        logger.warning("Background %s no encontrado, usando solido", path)
        return Image.new("RGBA", size, (30, 30, 60, 255))


def _center_text(draw: ImageDraw, text: str, font: ImageFont, y: int, color=WHITE) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (draw.im.size[0] - w) // 2
    draw.text((x, y), text, font=font, fill=color)


def _load_profile_photo(image_data: bytes | None, size: int = 60) -> Image.Image:
    if image_data:
        try:
            img = Image.open(BytesIO(image_data)).convert("RGBA")
            return img.resize((size, size), Image.LANCZOS)
        except Exception:
            pass
    # Placeholder por defecto
    try:
        placeholder = Image.open(_PLACEHOLDER_PATH).convert("RGBA")
        return placeholder.resize((size, size), Image.LANCZOS)
    except OSError:
        # Fallback: circulo gris
        img = Image.new("RGBA", (size, size), (80, 80, 100, 255))
        return img


def _paste_profile_photo(
    img: Image.Image, photo: Image.Image, x: int, y: int, size: int = 60
) -> None:
    """Recorta el photo en circular y pega la imagen en img en (x, y)

    Args:
        img (Image.Image): _description_
        photo (Image.Image): _description_
        x (int): _description_
        y (int): _description_
        size (int, optional): _description_. Defaults to 60.
    """
    # Crear mascara circular
    photo_resized = photo.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse([0, 0, size, size], fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(photo_resized, (0, 0), mask)
    img.paste(output, (x, y), output)


def generate_round_letter_image(
    letter: str,
    round_number: int,
    category_count: int = 8,
) -> bytes | None:
    try:
        img = _load_bg("round_bg.png", (256, 256))
        draw = ImageDraw.Draw(img)

        font_small = _get_font(20)
        _center_text(draw, f"RONDA {round_number}", font_small, 30, (200, 200, 255, 255))

        font_big = _get_font(100)
        _center_text(draw, letter.upper(), font_big, 75, WHITE)

        font_cat = _get_font(14)
        _center_text(draw, f"{category_count} categorias", font_cat, 210, (180, 180, 200, 255))

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.exception("Error generando imagen de letra: %s", e)
        return None


def generate_podium_image(
    winners: list[tuple[str, int]],
    game_rounds: int = 5,
    profile_photos: list[Image.Image | None] | None = None,
) -> bytes | None:
    try:
        img = _load_bg("podium_bg.png", (400, 300))
        draw = ImageDraw.Draw(img)

        font_title = _get_font(22)
        _center_text(draw, "PODIO FINAL", font_title, 12, GOLD)

        font_sub = _get_font(10)
        rondas_text = "1 ronda jugada" if game_rounds == 1 else f"{game_rounds} rondas jugadas"
        _center_text(draw, rondas_text, font_sub, 28, (180, 180, 190, 255))

        if not winners:
            _center_text(draw, "Sin puntuaciones", _get_font(18), 140, (255, 100, 100, 255))
            buf = BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return buf.getvalue()

        medals = ["1", "2", "3"]
        medal_colors = [GOLD, SILVER, BRONZE]

        for i, (name, score) in enumerate(winners[:3]):
            y = 52 + i * 78

            # Foto de perfil circular a la izquierda
            if profile_photos and i < len(profile_photos) and profile_photos[i]:
                _paste_profile_photo(img, profile_photos[i], 15, y, 42)

            # Medalla
            font_medal = _get_font(20)
            _center_text(draw, medals[i], font_medal, y + 5, medal_colors[i])

            # Nombre
            font_name = _get_font(13)
            _center_text(draw, name, font_name, y + 32, WHITE)

            # Puntaje
            font_score = _get_font(11)
            _center_text(draw, f"{score} pts", font_score, y + 52, medal_colors[i])

        if len(winners) > 3:
            font_rest = _get_font(9)
            rest_text = " | ".join(f"{i + 1}. {n}: {s}" for i, (n, s) in enumerate(winners[3:]))
            _center_text(draw, rest_text, font_rest, 275, (150, 150, 150, 255))

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.exception("Error generando imagen de podio: %s", e)
        return None


def generate_leaderboard_image(
    entries: list[tuple[int, str, int]],
    week_label: str = "Esta semana",
    profile_photos: dict[int, Image.Image] | None = None,
) -> bytes | None:
    try:
        img = Image.new("RGBA", (600, 800), (20, 20, 40, 255))
        draw = ImageDraw.Draw(img)

        font_title = _get_font(40)
        _center_text(draw, "TOP SEMANAL", font_title, 30, GOLD)

        font_sub = _get_font(22)
        _center_text(draw, week_label, font_sub, 75, (200, 200, 200, 255))

        if not entries:
            _center_text(draw, "Sin datos aun", _get_font(32), 380, (255, 100, 100, 255))
            buf = BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return buf.getvalue()

        font_entry = _get_font(28)
        font_score = _get_font(24)
        medals_emoji = {1: "1", 2: "2", 3: "3"}

        y = 130
        for rank, name, score in entries[:10]:
            prefix = medals_emoji.get(rank, f"{rank}.")
            display = f"{prefix} {name}"
            bbox = draw.textbbox((0, 0), display, font=font_entry)
            text_w = bbox[2] - bbox[0]
            x = (600 - text_w) // 2
            draw.text((x, y), display, font=font_entry, fill=WHITE)

            # Foto de perfil para top 3
            if profile_photos and rank in profile_photos and profile_photos[rank]:
                _paste_profile_photo(img, profile_photos[rank], 15, y - 5, 40)

            score_text = f"{score} pts"
            bbox2 = draw.textbbox((0, 0), score_text, font=font_score)
            score_x = 600 - (bbox2[2] - bbox2[0]) - 30
            draw.text((score_x, y + 5), score_text, font=font_score, fill=GOLD)

            y += 60

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.exception("Error generando leaderboard image: %s", e)
        return None


def generate_achievement_card(
    title: str,
    description: str,
    emoji: str = "T",
    color: tuple = (255, 215, 0),
) -> bytes | None:
    try:
        img = Image.new("RGBA", (400, 200), (25, 25, 50, 255))
        draw = ImageDraw.Draw(img)

        draw.rectangle([5, 5, 395, 195], outline=color, width=3)

        font_emoji = _get_font(64)
        _center_text(draw, emoji, font_emoji, 15)

        font_title = _get_font(32)
        _center_text(draw, title, font_title, 85, WHITE)

        font_desc = _get_font(20)
        _center_text(draw, description, font_desc, 125, (180, 180, 200, 255))

        font_tag = _get_font(16)
        _center_text(draw, "LOGRO DESBLOQUEADO", font_tag, 165, color)

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.exception("Error generando achievement card: %s", e)
        return None


def generate_activity_chart(daily_data: list[tuple[str, int]]) -> bytes | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.font_manager as fm
        import matplotlib.pyplot as plt

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
        ax.set_title("Actividad (7 dias)", color="white", fontsize=16, pad=15)
        ax.set_ylabel("Partidas", color="white")
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("#555")
        ax.spines["left"].set_color("#555")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height,
                    str(int(height)),
                    ha="center",
                    va="bottom",
                    color="white",
                )

        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=100, facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.exception("Error generando activity chart: %s", e)
        return None


def generate_welcome_image() -> bytes | None:
    try:
        img = Image.new("RGBA", (400, 300), (25, 25, 50, 255))
        draw = ImageDraw.Draw(img)

        borde_color = (100, 100, 200, 255)
        draw.rounded_rectangle([5, 5, 395, 295], radius=20, outline=borde_color, width=4)

        font_title = _get_font(28)
        _center_text(draw, "STOP", font_title, 40, (255, 215, 0, 255))

        font_subtitle = _get_font(16)
        _center_text(draw, "Pare!", font_subtitle, 80, (200, 200, 255, 255))

        # Cargar y sobreponer logo PNG centrado
        logo_path = os.path.join(_START_DIR, "stop_it.png")
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo = logo.resize((160, 160), Image.LANCZOS)
            logo_x = (400 - logo.width) // 2
            logo_y = (300 - logo.height) // 2 + 10  # +10 para ajuste vertical
            img.paste(logo, (logo_x, logo_y), logo)
        except OSError:
            logger.warning("Logo no encontrado en %s, omitiendo", logo_path)

        font_desc = _get_font(14)
        _center_text(draw, "Clasico juego de palabras", font_desc, 220, (180, 180, 200, 255))
        _center_text(draw, "en Telegram", font_desc, 245, (180, 180, 200, 255))

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.exception("Error generando imagen de bienvenida: %s", e)
        return None


def generate_help_image() -> bytes | None:
    try:
        img = Image.new("RGBA", (400, 300), (25, 25, 50, 255))
        draw = ImageDraw.Draw(img)

        borde_color = (100, 100, 200, 255)
        draw.rounded_rectangle([5, 5, 395, 295], radius=20, outline=borde_color, width=4)

        font_title = _get_font(24)
        _center_text(draw, "COMO JUGAR?", font_title, 25, (255, 215, 0, 255))

        # Cargar y sobreponer help.png centrado
        help_path = os.path.join(_HELP_DIR, "help.png")
        try:
            help_img = Image.open(help_path).convert("RGBA")
            help_img = help_img.resize((120, 120), Image.LANCZOS)
            help_x = (400 - help_img.width) // 2
            help_y = (300 - help_img.height) // 2 - 20
            img.paste(help_img, (help_x, help_y), help_img)
        except OSError:
            logger.warning("Help image no encontrada en %s, omitiendo", help_path)

        font_steps = _get_font(13)
        steps_y = 220
        pasos = [
            "1. /stop en grupo",
            "2. Espera jugadores (max. 10)",
            "3. Completa las categorias",
            "4. Se el primero en terminar",
        ]
        for paso in pasos:
            _center_text(draw, paso, font_steps, steps_y, (200, 200, 220, 255))
            steps_y += 18

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.exception("Error generando imagen de ayuda: %s", e)
        return None
