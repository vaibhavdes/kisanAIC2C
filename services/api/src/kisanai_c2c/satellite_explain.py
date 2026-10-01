"""Plain-language explanation of a satellite index map, in the farmer's language.

Built only from the measured zone areas of the map (no model text), so it always matches
the numbers shown. Classes 0-4 follow providers.satellite.INDEX_CLASSES.
"""

from __future__ import annotations

from typing import Any

LOCALES = ("en-IN", "hi-IN", "mr-IN", "te-IN", "kn-IN")

# Simple colour names per index and class, in en, hi, mr, te, kn.
SIMPLE_LABELS: dict[str, list[tuple[str, str, str, str, str]]] = {
    "NDVI": [
        ("Bare soil / no crop", "खाली ज़मीन / फसल नहीं", "मोकळी जमीन / पीक नाही", "ఖాళీ నేల / పంట లేదు", "ಖಾಲಿ ನೆಲ / ಬೆಳೆ ಇಲ್ಲ"),
        ("Weak crop", "कमज़ोर फसल", "कमजोर पीक", "బలహీన పంట", "ದುರ್ಬಲ ಬೆಳೆ"),
        ("Average crop", "औसत फसल", "मध्यम पीक", "సాధారణ పంట", "ಸಾಧಾರಣ ಬೆಳೆ"),
        ("Good crop", "अच्छी फसल", "चांगले पीक", "మంచి పంట", "ಉತ್ತಮ ಬೆಳೆ"),
        ("Very good, thick crop", "बहुत अच्छी, घनी फसल", "खूप चांगले, दाट पीक", "చాలా మంచి, దట్టమైన పంట", "ತುಂಬಾ ಉತ್ತಮ, ದಟ್ಟ ಬೆಳೆ"),
    ],
    "NDMI": [
        ("Very thirsty", "बहुत प्यासी", "खूप तहानलेले", "చాలా దాహం", "ತುಂಬಾ ಬಾಯಾರಿಕೆ"),
        ("Thirsty", "प्यासी", "तहानलेले", "దాహం", "ಬಾಯಾರಿಕೆ"),
        ("Some water", "थोड़ा पानी", "थोडे पाणी", "కొంత నీరు", "ಸ್ವಲ್ಪ ನೀರು"),
        ("Enough water", "पर्याप्त पानी", "पुरेसे पाणी", "తగినంత నీరు", "ಸಾಕಷ್ಟು ನೀರು"),
        ("Plenty of water", "भरपूर पानी", "भरपूर पाणी", "చాలా నీరు", "ಹೇರಳ ನೀರು"),
    ],
    "NDWI": [
        ("Dry ground", "सूखी ज़मीन", "कोरडी जमीन", "పొడి నేల", "ಒಣ ನೆಲ"),
        ("Slightly damp", "थोड़ी नम", "थोडी ओलसर", "కొంచెం తడి", "ಸ್ವಲ್ಪ ತೇವ"),
        ("Damp ground", "नम ज़मीन", "ओलसर जमीन", "తడి నేల", "ತೇವ ನೆಲ"),
        ("Very wet", "बहुत गीली", "खूप ओली", "చాలా తడి", "ತುಂಬಾ ಒದ್ದೆ"),
        ("Standing water", "जमा पानी", "साचलेले पाणी", "నిలిచిన నీరు", "ನಿಂತ ನೀರು"),
    ],
}

# (good classes, problem classes) per index.
GROUPS = {"NDVI": ({3, 4}, {0, 1}), "NDMI": ({3, 4}, {0, 1}), "NDWI": ({0, 1, 2}, {3, 4})}

T: dict[str, tuple[str, str, str, str, str]] = {
    "photo": (
        "Satellite photo of {date}.",
        "{date} की उपग्रह फोटो।",
        "{date} चा उपग्रह फोटो.",
        "{date} నాటి ఉపగ్రహ ఫోటో.",
        "{date} ರ ಉಪಗ್ರಹ ಫೋಟೋ.",
    ),
    "ndvi_good": (
        "{pct}% of the area ({acres} acres) has good green crop.",
        "{pct}% क्षेत्र ({acres} एकड़) में अच्छी हरी फसल है।",
        "{pct}% क्षेत्रात ({acres} एकर) चांगले हिरवे पीक आहे.",
        "{pct}% ప్రాంతంలో ({acres} ఎకరాలు) మంచి పచ్చని పంట ఉంది.",
        "{pct}% ಪ್ರದೇಶದಲ್ಲಿ ({acres} ಎಕರೆ) ಉತ್ತಮ ಹಸಿರು ಬೆಳೆ ಇದೆ.",
    ),
    "ndvi_bad": (
        "{pct}% ({acres} acres) has weak crop or bare soil: the red and orange patches. Walk to those patches and check for pests, lack of water or poor germination.",
        "{pct}% ({acres} एकड़) में कमज़ोर फसल या खाली ज़मीन है: लाल और नारंगी हिस्से। वहाँ जाकर कीट, पानी की कमी या खराब अंकुरण देखें।",
        "{pct}% ({acres} एकर) मध्ये कमजोर पीक किंवा मोकळी जमीन आहे: लाल व नारिंगी भाग. तिथे जाऊन कीड, पाण्याची कमतरता किंवा कमी उगवण तपासा.",
        "{pct}% ({acres} ఎకరాలు) లో బలహీన పంట లేదా ఖాళీ నేల ఉంది: ఎరుపు, నారింజ భాగాలు. అక్కడికి వెళ్లి పురుగులు, నీటి కొరత చూడండి.",
        "{pct}% ({acres} ಎಕರೆ) ದುರ್ಬಲ ಬೆಳೆ ಅಥವಾ ಖಾಲಿ ನೆಲ: ಕೆಂಪು, ಕಿತ್ತಳೆ ಭಾಗಗಳು. ಅಲ್ಲಿಗೆ ಹೋಗಿ ಕೀಟ, ನೀರಿನ ಕೊರತೆ ನೋಡಿ.",
    ),
    "ndvi_bare": (
        "Most of the area shows bare soil or very little crop. This is normal if the field is not yet sown or was just harvested.",
        "ज़्यादातर क्षेत्र में खाली ज़मीन या बहुत कम फसल दिख रही है। अगर अभी बुवाई नहीं हुई या कटाई हुई है तो यह सामान्य है।",
        "बहुतेक भागात मोकळी जमीन किंवा फार कमी पीक दिसते. पेरणी झाली नसेल किंवा काढणी झाली असेल तर हे सामान्य आहे.",
        "ఎక్కువ ప్రాంతంలో ఖాళీ నేల లేదా చాలా తక్కువ పంట కనిపిస్తోంది. విత్తకపోయినా, కోత అయినా ఇది సాధారణం.",
        "ಹೆಚ್ಚಿನ ಪ್ರದೇಶದಲ್ಲಿ ಖಾಲಿ ನೆಲ ಅಥವಾ ಕಡಿಮೆ ಬೆಳೆ ಕಾಣುತ್ತಿದೆ. ಬಿತ್ತನೆ ಆಗದಿದ್ದರೆ ಅಥವಾ ಕೊಯ್ಲು ಆಗಿದ್ದರೆ ಇದು ಸಾಮಾನ್ಯ.",
    ),
    "ndmi_good": (
        "In {pct}% of the area ({acres} acres) the leaves have enough water.",
        "{pct}% क्षेत्र ({acres} एकड़) में पत्तियों में पर्याप्त पानी है।",
        "{pct}% क्षेत्रात ({acres} एकर) पानांमध्ये पुरेसे पाणी आहे.",
        "{pct}% ప్రాంతంలో ({acres} ఎకరాలు) ఆకుల్లో తగినంత నీరు ఉంది.",
        "{pct}% ಪ್ರದೇಶದಲ್ಲಿ ({acres} ಎಕರೆ) ಎಲೆಗಳಲ್ಲಿ ಸಾಕಷ್ಟು ನೀರಿದೆ.",
    ),
    "ndmi_bad": (
        "In {pct}% ({acres} acres) the crop is thirsty: the red patches. If you can irrigate, water those parts first; otherwise cover the soil with straw to save moisture.",
        "{pct}% ({acres} एकड़) में फसल प्यासी है: लाल हिस्से। सिंचाई हो सके तो पहले वहाँ पानी दें; नहीं तो नमी बचाने के लिए पुआल बिछाएं।",
        "{pct}% ({acres} एकर) मध्ये पीक तहानलेले आहे: लाल भाग. पाणी देता आले तर आधी तिथे द्या; नाहीतर ओलावा टिकवण्यासाठी आच्छादन करा.",
        "{pct}% ({acres} ఎకరాలు) లో పంటకు దాహం: ఎరుపు భాగాలు. నీరు ఇవ్వగలిగితే ముందు అక్కడ ఇవ్వండి; లేకపోతే గడ్డి పరచండి.",
        "{pct}% ({acres} ಎಕರೆ) ಬೆಳೆಗೆ ಬಾಯಾರಿಕೆ: ಕೆಂಪು ಭಾಗಗಳು. ನೀರು ಕೊಡಲು ಸಾಧ್ಯವಾದರೆ ಮೊದಲು ಅಲ್ಲಿ ಕೊಡಿ; ಇಲ್ಲದಿದ್ದರೆ ಹುಲ್ಲು ಹಾಸಿ.",
    ),
    "ndwi_good": (
        "No standing water is seen; {pct}% of the area is dry or only damp.",
        "कहीं पानी जमा नहीं दिखता; {pct}% क्षेत्र सूखा या केवल नम है।",
        "कुठेही पाणी साचलेले दिसत नाही; {pct}% भाग कोरडा किंवा फक्त ओलसर आहे.",
        "ఎక్కడా నీరు నిలిచినట్టు లేదు; {pct}% ప్రాంతం పొడి లేదా కొంచెం తడి.",
        "ಎಲ್ಲೂ ನೀರು ನಿಂತಿಲ್ಲ; {pct}% ಪ್ರದೇಶ ಒಣ ಅಥವಾ ಸ್ವಲ್ಪ ತೇವ.",
    ),
    "ndwi_bad": (
        "{pct}% ({acres} acres) is very wet or has standing water: the dark blue patches. Open drains there so the roots do not rot.",
        "{pct}% ({acres} एकड़) बहुत गीला है या पानी जमा है: गहरे नीले हिस्से। जड़ें न सड़ें इसलिए वहाँ नाली खोलें।",
        "{pct}% ({acres} एकर) खूप ओला आहे किंवा पाणी साचले आहे: गडद निळे भाग. मुळे कुजू नयेत म्हणून तिथे चर काढा.",
        "{pct}% ({acres} ఎకరాలు) చాలా తడిగా ఉంది లేదా నీరు నిలిచింది: ముదురు నీలం భాగాలు. అక్కడ కాలువలు తెరవండి.",
        "{pct}% ({acres} ಎಕರೆ) ತುಂಬಾ ಒದ್ದೆ ಅಥವಾ ನೀರು ನಿಂತಿದೆ: ಕಡು ನೀಲಿ ಭಾಗಗಳು. ಅಲ್ಲಿ ಕಾಲುವೆ ತೆರೆಯಿರಿ.",
    ),
    "even": (
        "The field looks even, with no big problem patches.",
        "पूरा खेत एक जैसा दिखता है, कोई बड़ी समस्या वाला हिस्सा नहीं।",
        "संपूर्ण शेत एकसारखे दिसते, मोठा अडचणीचा भाग नाही.",
        "పొలం అంతా ఒకేలా ఉంది, పెద్ద సమస్య భాగాలు లేవు.",
        "ಹೊಲ ಎಲ್ಲೆಡೆ ಒಂದೇ ರೀತಿ ಇದೆ, ದೊಡ್ಡ ಸಮಸ್ಯೆ ಭಾಗ ಇಲ್ಲ.",
    ),
    "circle": (
        "This covers about 125 m around your farm point, which may include neighbouring fields. Draw your field boundary for an exact view.",
        "यह आपके खेत के बिंदु के आसपास लगभग 125 मीटर दिखाता है, इसमें पड़ोसी खेत भी हो सकते हैं। सटीक जानकारी के लिए खेत की सीमा बनाएं।",
        "हे तुमच्या शेताच्या बिंदूभोवती सुमारे 125 मीटर दाखवते, त्यात शेजारची शेते असू शकतात. अचूक माहितीसाठी शेताची हद्द आखा.",
        "ఇది మీ పొలం బిందువు చుట్టూ సుమారు 125 మీటర్లు చూపుతుంది, పక్క పొలాలు కూడా ఉండవచ్చు. ఖచ్చితత్వానికి పొలం హద్దు గీయండి.",
        "ಇದು ನಿಮ್ಮ ಹೊಲದ ಬಿಂದುವಿನ ಸುತ್ತ ಸುಮಾರು 125 ಮೀ ತೋರಿಸುತ್ತದೆ, ಪಕ್ಕದ ಹೊಲಗಳೂ ಇರಬಹುದು. ನಿಖರತೆಗೆ ಹೊಲದ ಗಡಿ ಬರೆಯಿರಿ.",
    ),
}


def _t(key: str, locale: str, **values: Any) -> str:
    return T[key][LOCALES.index(locale) if locale in LOCALES else 0].format(**values)


def simple_label(index: str, class_id: int, locale: str) -> str:
    labels = SIMPLE_LABELS.get(index)
    if not labels or not 0 <= class_id < len(labels):
        return ""
    return labels[class_id][LOCALES.index(locale) if locale in LOCALES else 0]


def explain_map(index: str, zones: list[Any], scene_date: str | None, has_boundary: bool, locale: str) -> str | None:
    """Two to four short sentences: what the colours show, how much area, and what to do."""
    if not zones:
        return None
    good_ids, bad_ids = GROUPS[index]
    good = [z for z in zones if z.id - 1 in good_ids]
    bad = [z for z in zones if z.id - 1 in bad_ids]
    good_pct = round(sum(z.percentage for z in good))
    bad_pct = round(sum(z.percentage for z in bad))
    good_acres = round(sum(z.area_acres for z in good), 1)
    bad_acres = round(sum(z.area_acres for z in bad), 1)
    key = index.lower()

    parts = [_t("photo", locale, date=scene_date)] if scene_date else []
    bare = next((z for z in zones if z.id == 1), None)
    if index == "NDVI" and bare and bare.percentage >= 50:
        parts.append(_t("ndvi_bare", locale))
    else:
        if good_pct:
            parts.append(_t(f"{key}_good", locale, pct=good_pct, acres=good_acres))
        if bad_pct >= 10:
            parts.append(_t(f"{key}_bad", locale, pct=bad_pct, acres=bad_acres))
        elif index != "NDWI":
            parts.append(_t("even", locale))
    if not has_boundary:
        parts.append(_t("circle", locale))
    return " ".join(parts)
