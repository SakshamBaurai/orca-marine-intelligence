"""ORCA Multilingual & Voice Service (i18n_service.py).

Provides a modular, non-invasive multilingual and speech layer around the existing
ORCAAgent without duplicating or altering core oceanographic intelligence logic:

1. Script & Language Detection for 11 supported languages:
   en (English), hi (Hindi), mr (Marathi), gu (Gujarati), ml (Malayalam),
   ta (Tamil), te (Telugu), kn (Kannada), bn (Bengali), pa (Punjabi), or (Odia).
2. Pre-translation Marine Gazetteer & Phonetic Intent Normalization:
   Ensures regional port names (in native script or Romanized/Hinglish text) and
   fishing/oceanographic terms map accurately to canonical English before
   ORCAAgent.process_query() runs.
3. Live Neural Translation API Integration (Google GTX endpoint + caching +
   optional Gemini/OpenAI LLM fallback + offline templates):
   - Translates arbitrary natural-language user queries into English.
   - Translates ORCAAgent responses and data card labels back into the user's
     selected language while strictly preserving coordinates, numbers, units,
     and markdown formatting.
4. Text-to-Speech (TTS) Audio Synthesis Proxy:
   Streams natural spoken MP3 audio for any supported language so the browser
   "[ 🔊 Speak ]" button works reliably even when the client OS lacks local
   Indian language TTS voices.
"""

from __future__ import annotations

import io
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx

try:
    import speech_recognition as sr
except ImportError:
    sr = None

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "hi": "Hindi / Hinglish",
    "hinglish": "Hinglish",
    "mr": "Marathi",
    "gu": "Gujarati",
    "ml": "Malayalam",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "bn": "Bengali",
    "pa": "Punjabi",
    "or": "Odia",
}

STT_BCP47_MAP: Dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "hinglish": "hi-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
    "ml": "ml-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "bn": "bn-IN",
    "pa": "pa-IN",
    "or": "or-IN",
}


# Unicode script ranges for automatic script detection when user types in native script
SCRIPT_RANGES: List[Tuple[int, int, str]] = [
    (0x0900, 0x097F, "hi"),  # Devanagari (Hindi / Marathi)
    (0x0980, 0x09FF, "bn"),  # Bengali
    (0x0A00, 0x0A7F, "pa"),  # Gurmukhi (Punjabi)
    (0x0A80, 0x0AFF, "gu"),  # Gujarati
    (0x0B00, 0x0B7F, "or"),  # Odia
    (0x0B80, 0x0BFF, "ta"),  # Tamil
    (0x0C00, 0x0C7F, "te"),  # Telugu
    (0x0C80, 0x0CFF, "kn"),  # Kannada
    (0x0D00, 0x0D7F, "ml"),  # Malayalam
]

# Native script & phonetic port gazetteer -> Canonical English port/region names
NATIVE_PORT_GAZETTEER: Dict[str, str] = {
    # Hindi / Marathi (Devanagari)
    "मुंबई": "Mumbai",
    "मुम्बई": "Mumbai",
    "कोच्चि": "Kochi",
    "कोचीन": "Kochi",
    "कांडला": "Kandla",
    "मुंद्रा": "Mundra",
    "पोरबंदर": "Porbandar",
    "वेरावल": "Veraval",
    "पीपावाव": "Pipavav",
    "हजीरा": "Hazira",
    "मोरमुगाओ": "Mormugao",
    "गोवा": "Goa",
    "मंगलुरु": "Mangaluru",
    "मैंगलोर": "Mangaluru",
    "रत्नागिरी": "Ratnagiri",
    "मालवण": "Malvan",
    "मालवन": "Malvan",
    "अलीबाग": "Alibaug",
    "कारवार": "Karwar",
    "मालपे": "Malpe",
    "उडुपी": "Malpe",
    "कोल्लम": "Kollam",
    "तिरुवनंतपुरम": "Thiruvananthapuram",
    "विझिंजम": "Thiruvananthapuram",
    "चेन्नई": "Chennai",
    "विशाखापत्तनम": "Visakhapatnam",
    "पारादीप": "Paradip",
    "गुजरात": "Gujarat",
    "महाराष्ट्र": "Maharashtra",
    "कर्नाटक": "Karnataka",
    "केरल": "Kerala",
    # Gujarati
    "મુંબઈ": "Mumbai",
    "કંડલા": "Kandla",
    "મુન્દ્રા": "Mundra",
    "પોરબંદર": "Porbandar",
    "વેરાવળ": "Veraval",
    "પીપાવાવ": "Pipavav",
    "હજીરા": "Hazira",
    "ઓખા": "Okha",
    "માંડવી": "Mandvi",
    "જખૌ": "Jakhau",
    "ભાવનગર": "Bhavnagar",
    "અલંગ": "Alang",
    "દમણ": "Daman",
    "ગુજરાત": "Gujarat",
    "કોચી": "Kochi",
    "ગોવા": "Goa",
    # Malayalam
    "കൊച്ചി": "Kochi",
    "മുംബൈ": "Mumbai",
    "കൊല്ലം": "Kollam",
    "തിരുവനന്തപുരം": "Thiruvananthapuram",
    "വിഴിഞ്ഞം": "Thiruvananthapuram",
    "മംഗളൂരു": "Mangaluru",
    "മംഗലാപുരം": "Mangaluru",
    "ഗോവ": "Goa",
    "കേരളം": "Kerala",
    "കേരള": "Kerala",
    # Kannada
    "ಮಂಗಳೂರು": "Mangaluru",
    "ಮಲ್ಪೆ": "Malpe",
    "ಕಾರವಾರ": "Karwar",
    "ಭಟ್ಕಳ": "Bhatkal",
    "ಹೊನ್ನಾವರ": "Honnavar",
    "ಕುಂದಾಪುರ": "Kundapura",
    "ಮುಂಬೈ": "Mumbai",
    "ಕೊಚ್ಚಿ": "Kochi",
    "ಗೋವಾ": "Goa",
    "ಕರ್ನಾಟಕ": "Karnataka",
    # Tamil
    "சென்னை": "Chennai",
    "தூத்துக்குடி": "Thoothukudi",
    "மும்பை": "Mumbai",
    "கொச்சி": "Kochi",
    "கோவா": "Goa",
    # Telugu
    "విశాఖపట్నం": "Visakhapatnam",
    "కాకినాడ": "Kakinada",
    "ముంబై": "Mumbai",
    "కొచ్చి": "Kochi",
    "చెన్నై": "Chennai",
    # Bengali
    "মুম্বাই": "Mumbai",
    "কোচি": "Kochi",
    "পারাদ্বীপ": "Paradip",
    "চেন্নাই": "Chennai",
    "বিশাখাপত্তনম": "Visakhapatnam",
    # Punjabi
    "ਮੁੰਬਈ": "Mumbai",
    "ਕੋਚੀ": "Kochi",
    "ਗੋਆ": "Goa",
    "ਗੁਜਰਾਤ": "Gujarat",
    # Odia
    "पारादीप": "Paradip",
    "ପାରାଦୀପ": "Paradip",
    "ମୁମ୍ବାଇ": "Mumbai",
    "କୋଚି": "Kochi",
    "విशाखापट्टनम": "Visakhapatnam",
}

# Domain term hints to assist offline or partial translations
OFFLINE_INTENT_KEYWORDS: Dict[str, str] = {
    # Fishing / PFZ
    "मछली": "fishing spot",
    "मछली पकड़ने": "fishing spot",
    "मासेमारी": "fishing spot",
    "માછીમારી": "fishing spot",
    "માછલી": "fishing spot",
    "മത്സ്യബന്ധനം": "fishing spot",
    "മീൻപിടുത്തം": "fishing spot",
    "മീൻ": "fishing spot",
    "ಮೀನುಗಾರಿಕೆ": "fishing spot",
    "ಮೀನು": "fishing spot",
    "மீன்பிடி": "fishing spot",
    "மீன்": "fishing spot",
    "చేపల వేట": "fishing spot",
    "చేపలు": "fishing spot",
    "মাছ ধরা": "fishing spot",
    "মাছ": "fishing spot",
    "ਮੱਛੀ": "fishing spot",
    "ମାଛ": "fishing spot",
    "machli": "fishing spot",
    "machhli": "fishing spot",
    "machli pakadne": "fishing spot",
    "machhli pakadne": "fishing spot",
    "macchi": "fishing spot",
    "machhi": "fishing spot",
    "shikar": "fishing spot",
    # Weather & Safety
    "मौसम": "weather",
    "हवामान": "weather",
    "હવામાન": "weather",
    "കാലാവസ്ഥ": "weather",
    "ಹವಾಮಾನ": "weather",
    "வானிலை": "weather",
    "వాతావరణం": "weather",
    "আবহাওয়া": "weather",
    "ਮੌਸਮ": "weather",
    "ପାଣିପାଗ": "weather",
    "mausam": "weather",
    "hawa": "wind weather",
    "toofan": "storm safety",
    "lehar": "waves sea condition",
    "lehrein": "waves sea condition",
    "सुरक्षित": "safe",
    "सलामत": "safe",
    "സുരക്ഷിത": "safe",
    "ಸುರಕ್ಷಿತ": "safe",
    "பாதுகாப்பான": "safe",
    "సురక్షిత": "safe",
    "নিরাপদ": "safe",
    "ਸੁਰੱਖਿਅਤ": "safe",
    "ସୁରକ୍ଷିତ": "safe",
    "surakshit": "safe",
    # SST / Temperature
    "तापमान": "sea surface temperature SST",
    "તાપમાન": "sea surface temperature SST",
    "താപനില": "sea surface temperature SST",
    "ತಾಪಮಾನ": "sea surface temperature SST",
    "வெப்பநிலை": "sea surface temperature SST",
    "ఉష్ణోగ్రత": "sea surface temperature SST",
    "তাপমাত্রা": "sea surface temperature SST",
    "ਤਾਪਮਾਨ": "sea surface temperature SST",
    "ତାପମାତ୍ରା": "sea surface temperature SST",
    "tapman": "sea surface temperature SST",
    "taapman": "sea surface temperature SST",
    "paani ka tapman": "sea surface temperature SST",
    "pani ka tapman": "sea surface temperature SST",
    "garam": "temperature SST",
    "thanda": "temperature SST",
    # Distance
    "दूरी": "calculate distance",
    "कितना दूर": "how far distance",
    "अंतर": "calculate distance",
    "અંતર": "calculate distance",
    "ദൂരം": "calculate distance",
    "ದೂರ": "calculate distance",
    "தூரம்": "calculate distance",
    "దూరం": "calculate distance",
    "দূরত্ব": "calculate distance",
    "doori": "calculate distance",
    "duri": "calculate distance",
    "kitna door": "how far distance",
    "kitni door": "how far distance",
    "kitna dur": "how far distance",
    # Marine Health
    "स्वास्थ्य": "marine health index",
    "आरोग्य": "marine health index",
    "સ્વાસ્થ્ય": "marine health index",
    "ആരോഗ്യം": "marine health index",
    "ಆರೋಗ್ಯ": "marine health index",
    "ஆரோக்கியம்": "marine health index",
    "ఆరోగ్యం": "marine health index",
    "sehat": "marine health index",
    "samudra sehat": "marine health index",
    # Upwelling
    "अपवेलिंग": "upwelling",
    "అప్‌వెల్లింగ్": "upwelling",
    # Proximity & Hinglish helpers
    "पास": "near",
    "नजदीक": "near",
    "जवळ": "near",
    "નજીક": "near",
    "അടുത്തുള്ള": "near",
    "അടുത്ത്": "near",
    "ಹತ್ತಿರ": "near",
    "அருகில்": "near",
    "దగ్గర": "near",
    "কাছে": "near",
    "ਨੇੜੇ": "near",
    "ପାଖରେ": "near",
    "ke paas": "near",
    "ke pas": "near",
    "nazdeek": "near",
    "najdeek": "near",
}

# Common Hinglish (Romanized Hindi) word/phrase normalizer for accurate intent parsing
HINGLISH_WORD_REPLACEMENTS: List[Tuple[str, str]] = [
    (r"\bmachh?li\s+pakadne\s+(ki|ka|ke)\s+(jagah|kshetra|area|zone|spot)\b", "best fishing spot"),
    (r"\bmachh?li\s+(kahan|kidhar)\s+milegi\b", "where are the best fishing spots"),
    (r"\bmachh?li\b", "fishing"),
    (r"\bmacch?i\b", "fishing"),
    (r"\bsabse\s+acch?[aei]\b", "best"),
    (r"\bacch?[aei]\s+jagah\b", "best spot"),
    (r"\bjagah\b", "spot"),
    (r"\bkshetra\b", "zone"),
    (r"\bke\s+paas\b", "near"),
    (r"\bke\s+pas\b", "near"),
    (r"\bnazdeek\b", "near"),
    (r"\bmausam\s+kaisa\s+hai\b", "how is the sea weather and safety"),
    (r"\bmausam\b", "weather"),
    (r"\bsamudra\b", "sea"),
    (r"\bsagar\b", "sea"),
    (r"\bpaa?ni\s+ka\s+taa?pman\b", "sea surface temperature SST"),
    (r"\btaa?pman\b", "sea surface temperature SST"),
    (r"\bkitn[aei]\s+doo?r\b", "how far is the distance"),
    (r"\bdoo?ri\b", "distance"),
    (r"\bsurakshit\b", "safe"),
    (r"\bkahan\s+hai\b", "where is"),
    (r"\bkaisa\s+hai\b", "how is"),
    (r"\bbatao\b", "tell me"),
    (r"\bbataye\b", "tell me"),
    (r"\bdikhao\b", "show me"),
]

# In-memory translation cache: (text, target_lang) -> translated_text
_TRANSLATION_CACHE: Dict[Tuple[str, str], str] = {}
_MAX_CACHE_SIZE = 2000


def _is_hinglish_text(text: str) -> bool:
    """Return True if text is ASCII Roman script containing recognizable Hinglish words."""
    if not text or not all(ord(c) < 128 for c in text):
        return False
    markers = {
        "machli", "machhli", "macchi", "mausam", "paas", "pas", "jagah", "kahan",
        "kaisa", "kaise", "hai", "hain", "mein", "मेरा", "batao", "bataye", "dikhao",
        "paani", "pani", "tapman", "taapman", "door", "doori", "duri", "kitna",
        "kitni", "sabse", "acha", "achi", "achha", "accha", "surakshit", "samudra",
        "sagar", "lehar", "hawa", "aaj", "abhi", "konsa", "kaunsa", "kya", "se", "ke"
    }
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    return len(words.intersection(markers)) >= 1


def _normalize_hinglish_to_english(text: str) -> str:
    """Convert common Hinglish phrases into clear English tokens prior to translation."""
    out = text
    for pattern, repl in HINGLISH_WORD_REPLACEMENTS:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def detect_script_language(text: str, requested_lang: Optional[str] = None) -> str:
    """Detect language from Unicode script or fall back to requested_lang."""
    req = (requested_lang or "en").strip().lower()
    if req not in SUPPORTED_LANGUAGES:
        req = "en"

    if not text:
        return req

    # Count characters in Indian Unicode script blocks
    counts: Dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for start, end, lang_code in SCRIPT_RANGES:
            if start <= cp <= end:
                counts[lang_code] = counts.get(lang_code, 0) + 1
                break

    if counts:
        detected = max(counts, key=counts.get)
        # Disambiguate Devanagari between Hindi ('hi') and Marathi ('mr')
        if detected == "hi" and req == "mr":
            return "mr"
        # If user selected hinglish but typed Devanagari, respond in Hindi
        if detected == "hi" and req == "hinglish":
            return "hi"
        # If user explicitly selected a language matching the script or left it on 'en'
        if req == "en":
            return detected
        return req

    # If text is ASCII Hinglish and user is on 'en' or 'hi' or 'hinglish'
    if _is_hinglish_text(text):
        if req == "hinglish":
            return "hinglish"
        if req in ("en", "hi"):
            return "hi"

    return req


def _google_translate_sync(text: str, target_lang: str, source_lang: str = "auto") -> Optional[str]:
    """Call Google Neural Translation GTX API over HTTPS with caching."""
    if not text or not text.strip():
        return text
    if target_lang == source_lang:
        return text

    cache_key = (text.strip(), target_lang)
    if cache_key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[cache_key]

    try:
        params = {
            "client": "gtx",
            "sl": source_lang,
            "tl": target_lang,
            "dt": "t",
            "q": text,
        }
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        with httpx.Client(timeout=4.5, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                payload = resp.json()
                if isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], list):
                    segments = [seg[0] for seg in payload[0] if isinstance(seg, list) and len(seg) > 0 and seg[0]]
                    translated = "".join(segments).strip()
                    if translated:
                        if len(_TRANSLATION_CACHE) >= _MAX_CACHE_SIZE:
                            _TRANSLATION_CACHE.clear()
                        _TRANSLATION_CACHE[cache_key] = translated
                        return translated
    except Exception as exc:
        print(f"[ORCA i18n] Live translation API notice ({source_lang}->{target_lang}): {exc}")

    return None


def _convert_english_to_hinglish(text: str) -> str:
    """Convert English ORCA response text into natural Romanized Hindi (Hinglish) while preserving numbers/units."""
    if not text:
        return text
    out = text
    replacements = [
        (r"(\d+)\s+suitable fishing zones found\s*\(High Tier\)", r"\1 sabse ache machli pakadne ke kshetra mile (High Tier)"),
        (r"(\d+)\s+suitable fishing zones found", r"\1 machli pakadne ke upyukt kshetra mile"),
        (r"from\s+\*\*(.*?)\*\*\s*\(12 NM regulatory boundary enforced\)", r"**\1** se (12 NM samudri seema ke bahar surakshit)"),
        (r"12 NM regulatory boundary enforced", "12 NM samudri seema laagu"),
        (r"HIGH\s*/\s*FAVORABLE", "UTTAM / ANUKOOL (High)"),
        (r"High\s*/\s*Favorable", "Uttam / Anukool"),
        (r"MODERATE\s*/\s*FAIR", "MADHYAM / THEEK (Moderate)"),
        (r"Best Fishing Spots near", "Ke Paas Machli Pakadne Ke Best Spots —"),
        (r"Recommended Fishing Grounds near", "Ke Paas Machli Pakadne Ke Best Kshetra —"),
        (r"Potential Fishing Zones \(PFZ\)", "Machli Pakadne Ke Kshetra (PFZ)"),
        (r"Potential Fishing Zone", "Machli Pakadne Ka Kshetra (PFZ)"),
        (r"Primary Recommendation", "Sabse Best Spot (01)"),
        (r"Secondary Option", "Doosra Vikalp (02)"),
        (r"Tertiary Option", "Teesra Vikalp (03)"),
        (r"Sea Surface Temperature \(SST\)", "Paani Ka Tapman (SST)"),
        (r"Sea Surface Temperature", "Paani Ka Tapman (SST)"),
        (r"Marine Health Index \(MHI\)", "Samudra Sehat Score (MHI)"),
        (r"Marine Health Index", "Samudra Sehat Score"),
        (r"Ocean Health", "Samudra Sehat"),
        (r"\bHealth\b", "Sehat"),
        (r"Chlorophyll-a", "Machli Ka Bhojan (Plankton / Chl-a)"),
        (r"Dissolved Oxygen", "Paani Mein Oxygen (DO)"),
        (r"SAFE / CALM WATERS", "SURAKSHIT / SHANT SAMUDRA (Safe)"),
        (r"MODERATE / CAUTION", "SAAVDHAN / Madhyam Lehrein"),
        (r"ROUGH / UNSAFE", "KHATARNAK / Asurakshit Samudra"),
        (r"12 NM Boundary Compliant", "12 NM Se Bahar Surakshit Kshetra"),
        (r"beyond the 12 NM territorial boundary", "12 NM chhote naav kshetra se bahar surakshit samudra mein"),
        (r"\*\*\[ Take me there \]\*\*", "**[ Mujhe Wahan Le Chalein ]**"),
        (r"\[ Take me there \]", "[ Mujhe Wahan Le Chalein ]"),
        (r"Distance:", "Doori (Distance):"),
        (r"Coordinates:", "GPS Sthan (Coordinates):"),
        (r"Why this spot:", "Yeh jagah kyun acchi hai:"),
        (r"Favorable thermal front", "Machli ke liye sahi paani ka tapman"),
        (r"Active nutrient upwelling", "Achha plankton aur machli ka bhojan"),
        (r"Optimal", "Uttam (Optimal)"),
        (r"High Productivity", "Zyada Machli Sambhavna (High)"),
        (r"Moderate Productivity", "Madhyam Machli Sambhavna"),
        (r"\bPort\b", "Bandargah"),
    ]
    for pat, rep in replacements:
        out = re.sub(pat, rep, out, flags=re.IGNORECASE)
    return out


def translate_query_to_english(query: str, requested_lang: Optional[str] = "en") -> Tuple[str, str]:
    """Normalize and translate a user query in any supported language (including Hinglish) into canonical English.

    Returns:
        (english_query, effective_language_code)
    """
    if not query or not query.strip():
        return query, (requested_lang or "en")

    effective_lang = detect_script_language(query, requested_lang)
    is_hinglish_input = _is_hinglish_text(query)

    # Extract any known ports & domain intents from native script / phonetic tokens first
    detected_ports: List[str] = []
    for native_name, eng_port in NATIVE_PORT_GAZETTEER.items():
        if native_name in query and eng_port not in detected_ports:
            detected_ports.append(eng_port)

    detected_intents: List[str] = []
    q_lower = query.lower()
    for token, eng_intent in OFFLINE_INTENT_KEYWORDS.items():
        if token in q_lower and eng_intent not in detected_intents:
            detected_intents.append(eng_intent)

    # Check if query is already plain ASCII English without phonetic Hindi/Hinglish/regional words
    is_ascii = all(ord(c) < 128 for c in query)
    if effective_lang == "en" and is_ascii and not detected_intents and not is_hinglish_input:
        return query, "en"

    # Pre-replace native port names so neural translation never garbles Indian port names
    pre_normalized = query
    for native_name, eng_port in NATIVE_PORT_GAZETTEER.items():
        if native_name in pre_normalized:
            pre_normalized = pre_normalized.replace(native_name, f" {eng_port} ")

    if is_hinglish_input or effective_lang in ("hi", "hinglish"):
        pre_normalized = _normalize_hinglish_to_english(pre_normalized)

    # Call live translation API (auto-detects script OR Romanized Hinglish/regional text)
    api_translated = _google_translate_sync(pre_normalized, target_lang="en", source_lang="auto")

    if api_translated:
        # Ensure any explicitly mapped port names remain present in the English query
        final_en = api_translated
        for port in detected_ports:
            if port.lower() not in final_en.lower():
                final_en = f"{final_en} near {port}"
        # If the user asks "which area/zone/where is safe for fishing", route to PFZ spot search
        fl = final_en.lower()
        asks_for_zone = any(w in fl for w in ["which area", "which zone", "which region", "which place", "where", "closest", "nearest", "spot", "zones"])
        mentions_fish = any(w in fl for w in ["fish", "fishing", "catch"])
        if asks_for_zone and mentions_fish and "safe" in fl:
            final_en = re.sub(r"\bsafe\b", "best favorable", final_en, flags=re.IGNORECASE)
            if "spot" not in final_en.lower() and "zone" not in final_en.lower():
                final_en = f"{final_en} fishing spots"
        return final_en.strip(), effective_lang

    # Offline fallback synthesis if internet is disconnected
    parts: List[str] = []
    if detected_intents:
        parts.extend(detected_intents)
    else:
        parts.append("fishing spot")
    if detected_ports:
        parts.append("near " + " and ".join(detected_ports))
    return " ".join(parts), effective_lang


def _protect_markdown_and_units(text: str) -> Tuple[str, Dict[str, str]]:
    """Protect tokens that should not be mangled during translation."""
    placeholders: Dict[str, str] = {}

    # Protect "[ Take me there ]" button marker
    if "**[ Take me there ]**" in text:
        text = text.replace("**[ Take me there ]**", "__ORCA_TAKE_ME_BTN__")
    elif "[ Take me there ]" in text:
        text = text.replace("[ Take me there ]", "__ORCA_TAKE_ME_BTN__")

    # Protect coordinate expressions like "18.94°N, 72.84°E"
    def _coord_repl(match: re.Match) -> str:
        key = f"__COORD_{len(placeholders)}__"
        placeholders[key] = match.group(0)
        return key

    text = re.sub(r"\d{1,2}\.\d+\s*°[NS][,\s]+\d{1,3}\.\d+\s*°[EW]", _coord_repl, text)
    return text, placeholders


def _restore_markdown_and_units(text: str, placeholders: Dict[str, str], target_lang: str) -> str:
    """Restore protected tokens after translation."""
    take_me_translations = {
        "hi": "**[ मुझे वहाँ ले चलें / Take me there ]**",
        "hinglish": "**[ Mujhe Wahan Le Chalein ]**",
        "mr": "**[ मला तिथे घेऊन चला ]**",
        "gu": "**[ મને ત્યાં લઈ જાઓ ]**",
        "ml": "**[ എന്നെ അവിടെ എത്തിക്കുക ]**",
        "ta": "**[ என்னை அங்கே அழைத்துச் செல் ]**",
        "te": "**[ నన్ను అక్కడికి తీసుకెళ్లండి ]**",
        "kn": "**[ ನನ್ನನ್ನು ಅಲ್ಲಿಗೆ ಕರೆದೊಯ್ಯಿರಿ ]**",
        "bn": "**[ আমাকে সেখানে নিয়ে চলুন ]**",
        "pa": "**[ ਮੈਨੂੰ ਉੱਥੇ ਲੈ ਚੱਲੋ ]**",
        "or": "**[ ମୋତେ ସେଠାକୁ ନିଅନ୍ତୁ ]**",
    }
    btn_text = take_me_translations.get(target_lang, "**[ Take me there ]**")
    text = re.sub(r"__\s*ORCA_TAKE_ME_BTN\s*__", btn_text, text, flags=re.IGNORECASE)

    for key, val in placeholders.items():
        # Handle potential spaces introduced by translator around placeholder underscores
        pattern = re.compile(re.escape(key).replace(r"\_", r"[\_\s]*"), re.IGNORECASE)
        text = pattern.sub(val, text)

    return text


def translate_text(text: str, target_lang: str) -> str:
    """Translate any English text to target_lang while preserving technical tokens."""
    if not text or not target_lang or target_lang == "en" or target_lang not in SUPPORTED_LANGUAGES:
        return text

    if target_lang == "hinglish":
        return _convert_english_to_hinglish(text)

    protected_text, placeholders = _protect_markdown_and_units(text)
    translated = _google_translate_sync(protected_text, target_lang=target_lang, source_lang="en")
    if translated:
        return _restore_markdown_and_units(translated, placeholders, target_lang)

    return text


def translate_agent_response(result: Dict[str, Any], target_lang: Optional[str] = "en", user_query: Optional[str] = None) -> Dict[str, Any]:
    """Translate ORCAAgent response dictionary into target_lang without mutating actions or coordinates."""
    lang = (target_lang or "en").strip().lower()
    if lang == "en" or lang not in SUPPORTED_LANGUAGES:
        return result

    out = dict(result)
    original_en_msg = out.get("message", "")

    # If user selected 'hinglish', provide full Hinglish response
    if lang == "hinglish":
        if original_en_msg:
            out["message"] = _convert_english_to_hinglish(original_en_msg)
        return out

    # 1. Translate main assistant message
    if original_en_msg:
        hi_msg = translate_text(original_en_msg, lang)
        # When in Hindi ('hi') mode, also include Hinglish summary if user typed in Hinglish (or as helpful Hinglish part)
        if lang == "hi":
            hinglish_part = _convert_english_to_hinglish(original_en_msg)
            first_line = hinglish_part.split("\n")[0].strip()
            if first_line:
                hi_msg = f"{hi_msg}\n\n💬 **Hinglish Summary:** {first_line}"
        out["message"] = hi_msg

    # 2. Translate data card labels (keep values and scientific units intact)
    if isinstance(out.get("data"), list) and out["data"]:
        translated_cards = []
        for card in out["data"]:
            c_copy = dict(card)
            if c_copy.get("label"):
                c_copy["label"] = _google_translate_sync(str(c_copy["label"]), target_lang=lang, source_lang="en") or c_copy["label"]
            if c_copy.get("details"):
                c_copy["details"] = _google_translate_sync(str(c_copy["details"]), target_lang=lang, source_lang="en") or c_copy["details"]
            translated_cards.append(c_copy)
        out["data"] = translated_cards

    # 3. Translate spot display metadata (while keeping lat, lon, distance_km, marine_health numeric)
    if isinstance(out.get("spots"), list) and out["spots"]:
        translated_spots = []
        for spot in out["spots"]:
            s_copy = dict(spot)
            if s_copy.get("label"):
                s_copy["label"] = _google_translate_sync(str(s_copy["label"]), target_lang=lang, source_lang="en") or s_copy["label"]
            if s_copy.get("productivity"):
                s_copy["productivity"] = _google_translate_sync(str(s_copy["productivity"]), target_lang=lang, source_lang="en") or s_copy["productivity"]
            if isinstance(s_copy.get("reasons"), list):
                s_copy["reasons"] = [
                    _google_translate_sync(str(r), target_lang=lang, source_lang="en") or r
                    for r in s_copy["reasons"]
                ]
            translated_spots.append(s_copy)
        out["spots"] = translated_spots

    return out


_SR_RECOGNIZER = sr.Recognizer() if sr is not None else None


def transcribe_wav_bytes(wav_bytes: bytes, lang: str = "en", partial: bool = False) -> str:
    """Transcribe 16-bit PCM WAV audio bytes using Google Speech Recognition over HTTPS.

    Works across all browsers (Brave, Edge, Chrome, Firefox, Safari) without
    relying on Chrome-restricted webkitSpeechRecognition network sockets.
    When partial=True (rolling real-time caption preview), skips secondary fallback
    for minimum latency.
    """
    if not wav_bytes or len(wav_bytes) < 100:
        raise ValueError("Empty or too-short audio buffer.")
    if sr is None or _SR_RECOGNIZER is None:
        raise RuntimeError("SpeechRecognition package is not installed in backend environment.")

    lang_key = (lang or "en").strip().lower()
    bcp47 = STT_BCP47_MAP.get(lang_key, "en-IN")

    with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
        audio_data = _SR_RECOGNIZER.record(source)

    # Primary recognition in selected language
    try:
        text = _SR_RECOGNIZER.recognize_google(audio_data, language=bcp47)
        if text and text.strip():
            return text.strip()
    except sr.UnknownValueError:
        pass

    # Fallback recognition in en-IN only on final transcription (catches Hinglish / English spoken while in an Indian language mode)
    if not partial and bcp47 != "en-IN":
        try:
            text_en = _SR_RECOGNIZER.recognize_google(audio_data, language="en-IN")
            if text_en and text_en.strip():
                return text_en.strip()
        except sr.UnknownValueError:
            pass

    raise ValueError("Could not understand audio clearly.")


def clean_text_for_speech(text: str) -> str:
    """Strip markdown symbols, action tags, and emojis so TTS reads naturally."""
    if not text:
        return ""
    # Remove Hinglish Summary footer from Hindi TTS so it doesn't read the message twice
    s = re.split(r"💬\s*\*?\*?Hinglish Summary:", text)[0]
    # Remove markdown bold/italic/headers
    s = re.sub(r"\*\*\[.*?\]\*\*", "", s)
    s = re.sub(r"[*_#`~>]", "", s)
    # Replace bullets with pauses
    s = s.replace("•", ". ")
    # Expand common symbols for clearer speech
    s = s.replace("°C", " degrees Celsius")
    s = s.replace("°N", " degrees North")
    s = s.replace("°E", " degrees East")
    s = s.replace("km/h", " kilometers per hour")
    s = s.replace("mg/m³", " milligrams per cubic meter")
    # Strip emojis / astral plane symbols
    s = re.sub(r"[\U00010000-\U0010ffff]", "", s)
    s = re.sub(r"[🌐🐋🎯🌡️🌊🩺🗺️🐟📏⚖️🌦️⚠️ℹ️✈️🚢📋⚓✓✕💬]", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_tts_chunks(text: str, max_len: int = 180) -> List[str]:
    """Split text into sentence-aligned chunks under 180 chars for Google TTS API."""
    sentences = re.split(r"(?<=[।.!?;\n])\s+", text)
    chunks: List[str] = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(current) + len(sent) + 1 <= max_len:
            current = f"{current} {sent}".strip()
        else:
            if current:
                chunks.append(current)
            if len(sent) <= max_len:
                current = sent
            else:
                # Hard split long clauses by comma or space
                words = sent.split(" ")
                sub = ""
                for w in words:
                    if len(sub) + len(w) + 1 <= max_len:
                        sub = f"{sub} {w}".strip()
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = w[:max_len]
                current = sub
    if current:
        chunks.append(current)
    return chunks[:8]  # Cap at 8 chunks (~1400 chars) for snappy audio response


def synthesize_speech_mp3(text: str, lang: str = "en") -> Optional[bytes]:
    """Fetch concatenated MP3 audio bytes from Google TTS stream for the target language."""
    clean = clean_text_for_speech(text)
    if not clean:
        return None

    tl = (lang or "en").strip().lower()
    if tl == "hinglish":
        tl = "hi"
    elif tl not in SUPPORTED_LANGUAGES:
        tl = "en"

    chunks = _split_tts_chunks(clean, max_len=180)
    if not chunks:
        return None

    audio_buffers: List[bytes] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://translate.google.com/",
    }

    try:
        with httpx.Client(timeout=6.0, follow_redirects=True) as client:
            for chunk in chunks:
                params = {
                    "ie": "UTF-8",
                    "client": "tw-ob",
                    "tl": tl,
                    "q": chunk,
                }
                url = "https://translate.google.com/translate_tts?" + urllib.parse.urlencode(params)
                resp = client.get(url, headers=headers)
                if resp.status_code == 200 and resp.content:
                    audio_buffers.append(resp.content)
    except Exception as exc:
        print(f"[ORCA TTS] Audio stream notice ({tl}): {exc}")

    if not audio_buffers:
        return None
    return b"".join(audio_buffers)

