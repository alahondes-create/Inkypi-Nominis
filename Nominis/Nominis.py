from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont
from utils.app_utils import get_font
import logging
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class Nominis(BasePlugin):
    LITERARY_STYLES = {
        "simple": {
            "name": "Style Simple",
            "description": "Réécris ce texte de manière claire et directe, sans ornements littéraires"
        },
        "claudel": {
            "name": "Paul Claudel",
            "description": "Réécris ce texte dans le style poétique de Paul Claudel, avec des phrases courtes, des métaphores spirituelles et une dimension mystique"
        },
        "hugo": {
            "name": "Victor Hugo",
            "description": "Réécris ce texte dans le style épique de Victor Hugo, avec des phrases longues, un vocabulaire riche et solennel, et des images grandioses"
        },
        "flaubert": {
            "name": "Gustave Flaubert",
            "description": "Réécris ce texte dans le style précis et réaliste de Gustave Flaubert, avec des descriptions détaillées et un souci du mot juste"
        },
        "baudelaire": {
            "name": "Charles Baudelaire",
            "description": "Réécris ce texte dans le style lyrique de Charles Baudelaire, avec des images poétiques, des contrastes saisissants et une touche de mélancolie"
        },
        "proust": {
            "name": "Marcel Proust",
            "description": "Réécris ce texte dans le style introspectif de Marcel Proust, avec des phrases longues et sinueuses, explorant les nuances de la mémoire et du temps"
        },
        "zola": {
            "name": "Émile Zola",
            "description": "Réécris ce texte dans le style naturaliste d'Émile Zola, avec des descriptions précises et un regard réaliste sur la société"
        },
        "verlaine": {
            "name": "Paul Verlaine",
            "description": "Réécris ce texte dans le style musical et mélodique de Paul Verlaine, avec une attention particulière à la sonorité des mots"
        },
        "rimbaud": {
            "name": "Arthur Rimbaud",
            "description": "Réécris ce texte dans le style visionnaire et surréaliste d'Arthur Rimbaud, avec des images audacieuses et une touche de rébellion"
        },
        "balzac": {
            "name": "Honoré de Balzac",
            "description": "Réécris ce texte dans le style réaliste et descriptif de Balzac, avec une attention aux détails de la société et des personnages"
        }
    }

    def _fetch_saint_of_the_day(self):
    """Récupère le saint du jour et sa description depuis la page d'accueil de Nominis."""
        url = "https://nominis.cef.fr/"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Tr    ouver le premier <h2> (nom du saint)
            saint_h2 = soup.find("h2")
            if not saint_h2:
                return None

            saint_nom = saint_h2.get_text(strip=True)

            # Extraire TOUS les paragraphes et textes après le <h2> jusqu'au prochain titre majeur
            biographie_paragraphes = []
            current = saint_h2.find_next()
            while current:
                # Arrêter si on trouve un titre de section suivante (h1, h2, h4, etc.)
                if current.name in ["h1", "h2", "h4", "h5", "h6"]:
                    break
                # Si c'est un paragraphe ou un texte direct
                if current.name == "p" or (current.name is None and current.strip()):
                    texte = current.get_text(strip=True) if current.name else current.strip()
                    if texte and len(texte) > 10:  # Ignorer les textes trop courts (espaces, etc.)
                        biographie_paragraphes.append(texte)
                current = current.find_next()

            biographie = " ".join(biographie_paragraphes)
        return saint_nom, biographie

        except Exception as e:
            logger.error(f"Error: {e}")
            return None, None

    def _call_lechat_api(self, text, word_limit, style_key, api_key, model="mistral-medium"):
        if not text or not api_key:
            return None

        style = self.LITERARY_STYLES.get(style_key, self.LITERARY_STYLES["simple"])

        prompt = f"""Tu es un expert en littérature française. Réécris le texte suivant dans le style de {style['name']}.

Instructions précises :
1. Respecte le style de {style['name']} : {style['description']}
2. Limite-toi à environ {word_limit} mots maximum
3. Conserve le sens original du texte
4. Utilise un français élégant et naturel
5. Ne commence pas par "Voici" ou "Voilà"
6. Ne mentionne pas que tu réécris le texte
7. Ne met pas le résultat entre guillemets

Texte à réécrire :
{text}"""

        try:
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 500,
                "top_p": 0.9
            }
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            if 'choices' in data and len(data['choices']) > 0:
                synthesized_text = data['choices'][0]['message']['content'].strip()
                words = synthesized_text.split()
                if len(words) > word_limit:
                    synthesized_text = ' '.join(words[:word_limit])
                    last_punct = max([i for i, w in enumerate(words[:word_limit]) if w.endswith(('.', '!', '?'))], default=-1)
                    if last_punct > word_limit - 5:
                        synthesized_text = ' '.join(words[:last_punct + 1])
                    synthesized_text += "..."
                return synthesized_text
            return None
        except Exception as e:
            logger.error(f"Mistral API Error: {e}")
            return None

    def _wrap_text(self, text, font, max_width):
        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                continue
            words = paragraph.split(' ')
            current_line = words[0] if words else ''
            for word in words[1:]:
                test_line = f"{current_line} {word}"
                if font.getbbox(test_line)[2] - font.getbbox(test_line)[0] <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
        return lines

    def generate_image(self, settings, device_config):
        word_limit = int(settings.get("word_limit", "50"))
        style_key = settings.get("style", "simple")
        font_size_multiplier = float(settings.get("font_size", "0.1"))
        show_date = settings.get("show_date", "true").lower() == "true"
        model = settings.get("model", "mistral-medium")

        api_key = settings.get("api_key", "")
        if not api_key:
            api_key = device_config.load_env_key("MISTRAL_API_KEY")

        if not api_key:
            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "vertical":
                dimensions = dimensions[::-1]
            width, height = dimensions
            image = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(image)
            font = get_font("Jost", int(width * 0.07))
            error_lines = ["Clé API Mistral", "manquante", "", "Configurez MISTRAL_API_KEY", "dans .env ou paramètres"]
            y = (height - len(error_lines) * width * 0.07) // 2
            for line in error_lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                draw.text(((width - bbox[2]) // 2, y), line, fill="black", font=font)
                y += width * 0.08
            return image

        saint_name, saint_description = self._fetch_saint_of_the_day()
        if not saint_name or not saint_description:
            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "vertical":
                dimensions = dimensions[::-1]
            width, height = dimensions
            image = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(image)
            font = get_font("Jost", int(width * 0.08))
            error_lines = ["Impossible de", "charger le saint", "du jour"]
            y = (height - len(error_lines) * width * 0.08) // 2
            for line in error_lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                draw.text(((width - bbox[2]) // 2, y), line, fill="black", font=font)
                y += width * 0.09
            return image

        synthesized = self._call_lechat_api(saint_description, word_limit, style_key, api_key, model)
        if not synthesized:
            logger.warning("Mistral API failed, falling back to truncation")
            words = saint_description.split()
            synthesized = ' '.join(words[:word_limit]) + ("..." if len(words) > word_limit else "")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        width, height = dimensions

        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        font_size = int(width * font_size_multiplier)
        title_font = get_font("Jost", int(font_size * 1.3), bold=True)
        body_font = get_font("Jost", font_size)
        date_font = get_font("Jost", int(font_size * 0.8))

        today = datetime.now().strftime("%d %B %Y") if show_date else ""
        full_text = f"{today}\n\n{saint_name}\n\n{synthesized}" if show_date else f"{saint_name}\n\n{synthesized}"
        lines = self._wrap_text(full_text, body_font, width * 0.95)
        line_height = font_size * 1.3
        total_height = len(lines) * line_height

        for _ in range(5):
            if total_height <= height * 0.95:
                break
            font_size = int(font_size * 0.9)
            title_font = get_font("Jost", int(font_size * 1.3), bold=True)
            body_font = get_font("Jost", font_size)
            line_height = font_size * 1.3
            lines = self._wrap_text(full_text, body_font, width * 0.95)
            total_height = len(lines) * line_height

        y = (height - total_height) // 2
        for line in lines:
            if not line.strip():
                continue
            if line.strip() == saint_name:
                font = title_font
                bbox = draw.textbbox((0, 0), line, font=font)
                draw.text(((width - bbox[2]) // 2, y), line, fill="black", font=font)
                y += line_height * 1.2
            elif show_date and line.strip() == today:
                font = date_font
                bbox = draw.textbbox((0, 0), line, font=font)
                draw.text(((width - bbox[2]) // 2, y), line, fill="#666666", font=font)
                y += line_height * 0.8
            else:
                font = body_font
                bbox = draw.textbbox((0, 0), line, font=font)
                draw.text(((width - bbox[2]) // 2, y), line, fill="black", font=font)
                y += line_height

        return image

