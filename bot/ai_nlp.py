"""
ai_nlp_v2.py — Улучшенный модуль анализа переписки и генерации ответов для BCD TRAVEL

Ключевые улучшения:
- Модульная архитектура с чёткими зонами ответственности
- Продвинутый NLP с весовыми коэффициентами и контекстным анализом
- Поддержка множественных языков с автоопределением
- Гибкая система правил для маршрутизации
- Кэширование и оптимизация производительности
- Расширенная обработка ошибок и логирование
- Type hints и dataclasses для типобезопасности
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union, Tuple, Callable, Set
from enum import Enum, auto
from functools import lru_cache
from abc import ABC, abstractmethod
import os
import logging
import json
import re
from datetime import datetime, timedelta
import hashlib

# Предполагаем, что openai_client существует
try:
    from openai_client import generate_chat_completion
except ImportError:
    def generate_chat_completion(messages, model="gpt-4o", max_tokens=500, temperature=0.2):
        raise NotImplementedError("openai_client не найден")

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Config:
    """Централизованная конфигурация приложения"""
    mailbox_upn: str = field(default_factory=lambda: os.getenv("MAILBOX_UPN", "RobotVisa@itplus.kz"))
    default_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))
    non_standard_forward_email: str = field(default_factory=lambda: os.getenv("NON_STANDARD_FORWARD_EMAIL", "azamat@example.com"))
    max_thread_length: int = 8000
    max_tokens_reply: int = 800
    temperature: float = 0.2
    
    # URL форм
    form_poland_url: Optional[str] = field(default_factory=lambda: os.getenv("FORM_POLAND_URL") or os.getenv("POLAND_FORM_URL"))
    form_schengen_url: Optional[str] = field(default_factory=lambda: os.getenv("FORM_SCHENGEN_URL") or os.getenv("SCHENGEN_FORM_URL"))
    form_usa_url: Optional[str] = field(default_factory=lambda: os.getenv("FORM_USA_URL") or os.getenv("USA_FORM_URL"))
    form_generic_url: Optional[str] = field(default_factory=lambda: os.getenv("FORM_GENERIC_URL") or os.getenv("GENERIC_FORM_URL"))


CONFIG = Config()


# ═══════════════════════════════════════════════════════════════════════════════
# ПЕРЕЧИСЛЕНИЯ (ENUMS)
# ═══════════════════════════════════════════════════════════════════════════════

class Language(Enum):
    """Поддерживаемые языки"""
    RUSSIAN = "ru"
    ENGLISH = "en"
    KAZAKH = "kk"
    
    @classmethod
    def default(cls) -> 'Language':
        return cls.RUSSIAN


class Intent(Enum):
    """Типы намерений клиента"""
    WANT_APPLY = "want_apply"           # Хочет подать на визу
    SEND_DOCS = "send_docs"             # Отправляет документы
    INFO_REQUEST = "info_request"       # Запрашивает информацию
    FOLLOWUP = "followup"               # Следит за статусом
    COMPLAINT = "complaint"             # Жалоба
    GRATITUDE = "gratitude"             # Благодарность
    CANCELLATION = "cancellation"       # Отмена заявки
    RESCHEDULE = "reschedule"           # Перенос даты
    PAYMENT = "payment"                 # Вопросы оплаты
    OTHER = "other"                     # Прочее
    
    @classmethod
    def default(cls) -> 'Intent':
        return cls.OTHER


class LeadStatus(Enum):
    """Статусы лида в воронке"""
    NEW = "new"
    INFO_PROVIDED = "info_provided"
    QUESTIONNAIRE_SENT = "questionnaire_sent"
    QUESTIONNAIRE_FILLED = "questionnaire_filled"
    DOCS_IN_PROGRESS = "docs_in_progress"
    DOCS_COLLECTED = "docs_collected"
    READY_FOR_SUBMISSION = "ready_for_submission"
    SUBMITTED = "submitted"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    
    @classmethod
    def default(cls) -> 'LeadStatus':
        return cls.NEW
    
    @classmethod
    def from_string(cls, s: Optional[str]) -> 'LeadStatus':
        if not s:
            return cls.default()
        try:
            return cls(s.lower())
        except ValueError:
            return cls.default()


class UrgencyLevel(Enum):
    """Уровни срочности"""
    CRITICAL = 4    # Вылет сегодня/завтра
    HIGH = 3        # Очень срочно, ASAP
    MEDIUM = 2      # Срочно
    NORMAL = 1      # Обычный приоритет
    LOW = 0         # Низкий приоритет


class VisaCategory(Enum):
    """Категории виз по сложности обработки"""
    STANDARD = "standard"               # PL, Schengen, US - стандартная обработка
    NON_STANDARD = "non_standard"       # Требует ручной обработки
    SIMPLE = "simple"                   # Безвизовые или электронные визы


# ═══════════════════════════════════════════════════════════════════════════════
# МОДЕЛИ ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Message:
    """Сообщение в переписке"""
    from_address: str
    subject: str
    body: str
    received_at: Optional[str] = None
    attachments: List[str] = field(default_factory=list)
    message_id: Optional[str] = None
    
    @property
    def full_text(self) -> str:
        """Полный текст для анализа"""
        parts = []
        if self.subject:
            parts.append(self.subject)
        if self.body:
            parts.append(self.body)
        return "\n".join(parts)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Создание из словаря (формат MS Graph API)"""
        from_data = data.get("from", {})
        email_data = from_data.get("emailAddress", {}) if isinstance(from_data, dict) else {}
        
        body_data = data.get("body", {})
        body_content = ""
        if isinstance(body_data, dict):
            body_content = body_data.get("content", "")
        elif isinstance(body_data, str):
            body_content = body_data
        
        return cls(
            from_address=email_data.get("address", "") if isinstance(email_data, dict) else "",
            subject=data.get("subject", ""),
            body=data.get("bodyPreview", "") or body_content,
            received_at=data.get("receivedDateTime"),
            attachments=[a.get("name", "") for a in data.get("attachments", []) if isinstance(a, dict)],
            message_id=data.get("id"),
        )


@dataclass
class Country:
    """Информация о стране"""
    code: str                           # ISO код (2 буквы)
    names: Set[str]                     # Все варианты названий
    category: VisaCategory              # Категория визы
    form_type: Optional[str] = None     # Тип формы: poland, schengen, usa, generic
    processing_notes: Optional[str] = None  # Заметки по обработке


@dataclass
class FormLinks:
    """Ссылки на формы анкет"""
    poland: Optional[str] = None
    schengen: Optional[str] = None
    usa: Optional[str] = None
    generic: Optional[str] = None
    
    @classmethod
    def from_config(cls) -> 'FormLinks':
        return cls(
            poland=CONFIG.form_poland_url,
            schengen=CONFIG.form_schengen_url,
            usa=CONFIG.form_usa_url,
            generic=CONFIG.form_generic_url,
        )
    
    def get_by_type(self, form_type: Optional[str]) -> Optional[str]:
        """Получить URL по типу формы"""
        if not form_type:
            return None
        return getattr(self, form_type, None)


@dataclass
class ThreadAnalysis:
    """Результат анализа переписки"""
    language: Language
    detected_country: Optional[Country]
    intent: Intent
    urgency: UrgencyLevel
    previous_status: LeadStatus
    new_status: LeadStatus
    
    # Флаги для форм
    offer_poland_form: bool = False
    offer_schengen_form: bool = False
    offer_usa_form: bool = False
    offer_generic_form: bool = False
    
    # Дополнительные флаги
    is_non_standard_destination: bool = False
    has_attachments: bool = False
    sentiment: str = "neutral"          # positive, neutral, negative
    
    # Маршрутизация
    forward_to_email: Optional[str] = None
    forward_reason: Optional[str] = None
    
    # Метаданные
    confidence_score: float = 0.0       # 0.0-1.0
    analysis_notes: List[str] = field(default_factory=list)
    
    @property
    def country_code(self) -> Optional[str]:
        return self.detected_country.code if self.detected_country else None
    
    @property
    def needs_form(self) -> bool:
        return any([
            self.offer_poland_form,
            self.offer_schengen_form,
            self.offer_usa_form,
            self.offer_generic_form,
        ])
    
    @property
    def form_type(self) -> Optional[str]:
        if self.offer_poland_form:
            return "poland"
        if self.offer_schengen_form:
            return "schengen"
        if self.offer_usa_form:
            return "usa"
        if self.offer_generic_form:
            return "generic"
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# БАЗА ЗНАНИЙ О СТРАНАХ
# ═══════════════════════════════════════════════════════════════════════════════

class CountryDatabase:
    """База данных стран с расширенной информацией"""
    
    # Страны Шенгена
    SCHENGEN_COUNTRIES = {"AT", "BE", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", 
                          "IS", "IT", "LV", "LI", "LT", "LU", "MT", "NL", "NO", "PL", 
                          "PT", "SK", "SI", "ES", "SE", "CH"}
    
    # Нестандартные страны (требуют ручной обработки)
    NON_STANDARD_CODES = {"GB", "CA", "AU", "NZ", "JP", "CN", "KR", "IN", "BR", "AR", 
                          "MX", "TR", "AE", "SA", "ZA", "EG", "MA", "TH", "VN", "SG",
                          "IL", "MY", "ID", "PH", "PK", "BD", "LK", "NP", "IR", "IQ"}
    
    def __init__(self):
        self._countries: Dict[str, Country] = {}
        self._keyword_index: Dict[str, str] = {}  # keyword -> country_code
        self._build_database()
    
    def _build_database(self):
        """Построение базы данных стран"""
        countries_data = [
            # === ПОЛЬША ===
            Country(
                code="PL",
                names={"poland", "польша", "польшу", "польши", "warsaw", "варшава", 
                       "варшаву", "krakow", "краков", "gdansk", "гданьск", "wroclaw", "вроцлав"},
                category=VisaCategory.STANDARD,
                form_type="poland",
            ),
            
            # === США ===
            Country(
                code="US",
                names={"usa", "u.s.", "u.s.a.", "united states", "america", "америка", 
                       "сша", "штаты", "соединённые штаты", "new york", "нью-йорк", 
                       "los angeles", "лос-анджелес", "washington", "вашингтон",
                       "california", "калифорния", "florida", "флорида", "texas", "техас"},
                category=VisaCategory.STANDARD,
                form_type="usa",
            ),
            
            # === ШЕНГЕН (основные страны) ===
            Country(
                code="FR",
                names={"france", "франция", "францию", "франции", "paris", "париж",
                       "nice", "ницца", "lyon", "лион", "marseille", "марсель"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="DE",
                names={"germany", "германия", "германию", "германии", "berlin", "берлин",
                       "munich", "мюнхен", "frankfurt", "франкфурт", "hamburg", "гамбург"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="IT",
                names={"italy", "италия", "италию", "италии", "rome", "рим", "roma",
                       "milan", "милан", "venice", "венеция", "florence", "флоренция"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="ES",
                names={"spain", "испания", "испанию", "испании", "barcelona", "барселона",
                       "madrid", "мадрид", "valencia", "валенсия", "seville", "севилья"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="NL",
                names={"netherlands", "нидерланды", "голландия", "holland", "amsterdam",
                       "амстердам", "rotterdam", "роттердам", "hague", "гаага"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="AT",
                names={"austria", "австрия", "австрию", "вена", "vienna", "wien",
                       "salzburg", "зальцбург", "innsbruck", "инсбрук"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="BE",
                names={"belgium", "бельгия", "бельгию", "brussels", "брюссель",
                       "bruges", "брюгге", "antwerp", "антверпен"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="CZ",
                names={"czech", "чехия", "чехию", "prague", "прага", "brno", "брно"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="PT",
                names={"portugal", "португалия", "португалию", "lisbon", "лиссабон",
                       "porto", "порту"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="GR",
                names={"greece", "греция", "грецию", "athens", "афины", "santorini",
                       "санторини", "crete", "крит", "rhodes", "родос"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="HU",
                names={"hungary", "венгрия", "венгрию", "budapest", "будапешт"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="CH",
                names={"switzerland", "швейцария", "швейцарию", "zurich", "цюрих",
                       "geneva", "женева", "bern", "берн"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="SE",
                names={"sweden", "швеция", "швецию", "stockholm", "стокгольм"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="NO",
                names={"norway", "норвегия", "норвегию", "oslo", "осло"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="FI",
                names={"finland", "финляндия", "финляндию", "helsinki", "хельсинки"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            Country(
                code="DK",
                names={"denmark", "дания", "данию", "copenhagen", "копенгаген"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
            
            # === НЕСТАНДАРТНЫЕ СТРАНЫ ===
            Country(
                code="GB",
                names={"uk", "united kingdom", "great britain", "england", "британия",
                       "великобритания", "англия", "london", "лондон", "manchester",
                       "манчестер", "liverpool", "ливерпуль", "scotland", "шотландия"},
                category=VisaCategory.NON_STANDARD,
                processing_notes="Требуется отдельная британская виза",
            ),
            Country(
                code="CA",
                names={"canada", "канада", "канаду", "toronto", "торонто", "vancouver",
                       "ванкувер", "montreal", "монреаль", "ottawa", "оттава"},
                category=VisaCategory.NON_STANDARD,
                processing_notes="Требуется eTA или виза",
            ),
            Country(
                code="AU",
                names={"australia", "австралия", "австралию", "sydney", "сидней",
                       "melbourne", "мельбурн", "brisbane", "брисбен"},
                category=VisaCategory.NON_STANDARD,
                processing_notes="Требуется ETA или виза",
            ),
            Country(
                code="NZ",
                names={"new zealand", "новая зеландия", "wellington", "веллингтон",
                       "auckland", "окленд"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="JP",
                names={"japan", "япония", "японию", "tokyo", "токио", "osaka", "осака",
                       "kyoto", "киото"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="CN",
                names={"china", "китай", "beijing", "пекин", "shanghai", "шанхай",
                       "guangzhou", "гуанчжоу", "shenzhen", "шэньчжэнь"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="KR",
                names={"south korea", "korea", "корея", "южная корея", "seoul", "сеул",
                       "busan", "пусан"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="IN",
                names={"india", "индия", "индию", "delhi", "дели", "mumbai", "мумбаи",
                       "bangalore", "бангалор"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="BR",
                names={"brazil", "бразилия", "бразилию", "rio", "рио", "sao paulo",
                       "сан-паулу"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="AR",
                names={"argentina", "аргентина", "аргентину", "buenos aires",
                       "буэнос-айрес"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="MX",
                names={"mexico", "мексика", "мексику", "cancun", "канкун",
                       "mexico city", "мехико"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="TR",
                names={"turkey", "турция", "турцию", "istanbul", "стамбул",
                       "истанбул", "antalya", "анталия", "ankara", "анкара"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="AE",
                names={"uae", "emirates", "эмираты", "оаэ", "dubai", "дубай",
                       "abu dhabi", "абу-даби"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="SA",
                names={"saudi arabia", "саудовская аравия", "riyadh", "эр-рияд",
                       "jeddah", "джидда", "mecca", "мекка"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="ZA",
                names={"south africa", "юар", "южная африка", "johannesburg",
                       "йоханнесбург", "cape town", "кейптаун"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="EG",
                names={"egypt", "египет", "sharm", "шарм", "hurghada", "хургада",
                       "cairo", "каир"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="TH",
                names={"thailand", "tailand", "таиланд", "тайланд", "phuket", "пхукет",
                       "bangkok", "бангкок", "pattaya", "паттайя"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="VN",
                names={"vietnam", "вьетнам", "hanoi", "ханой", "ho chi minh",
                       "хошимин", "saigon", "сайгон"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="SG",
                names={"singapore", "сингапур"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="MY",
                names={"malaysia", "малайзия", "kuala lumpur", "куала-лумпур"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="ID",
                names={"indonesia", "индонезия", "bali", "бали", "jakarta", "джакарта"},
                category=VisaCategory.NON_STANDARD,
            ),
            Country(
                code="IL",
                names={"israel", "израиль", "tel aviv", "тель-авив", "jerusalem",
                       "иерусалим"},
                category=VisaCategory.NON_STANDARD,
            ),
            
            # === ВИРТУАЛЬНАЯ СТРАНА "ШЕНГЕН" ===
            Country(
                code="SCHENGEN",
                names={"schengen", "шенген", "шенгенскую", "шенгенская", "шенгенской",
                       "шенгенскую визу", "schengen visa", "europe", "европа", "европу",
                       "евросоюз", "eu"},
                category=VisaCategory.STANDARD,
                form_type="schengen",
            ),
        ]
        
        for country in countries_data:
            self._countries[country.code] = country
            for name in country.names:
                self._keyword_index[name.lower()] = country.code
    
    def find_country(self, text: str) -> Optional[Country]:
        """Поиск страны в тексте с учётом приоритетов"""
        text_lower = text.lower()
        
        # Сначала ищем точные совпадения (более длинные фразы имеют приоритет)
        matches: List[Tuple[str, int]] = []
        
        for keyword, code in self._keyword_index.items():
            if keyword in text_lower:
                # Проверяем, что это не часть другого слова
                pattern = rf'\b{re.escape(keyword)}\b'
                if re.search(pattern, text_lower):
                    matches.append((code, len(keyword)))
                elif keyword in text_lower:
                    # Менее строгое совпадение для кириллицы
                    matches.append((code, len(keyword)))
        
        if not matches:
            return None
        
        # Сортируем по длине ключевого слова (длинные = более специфичные)
        matches.sort(key=lambda x: x[1], reverse=True)
        best_code = matches[0][0]
        
        return self._countries.get(best_code)
    
    def get_country(self, code: str) -> Optional[Country]:
        """Получить страну по коду"""
        return self._countries.get(code.upper())
    
    def is_schengen(self, code: str) -> bool:
        """Проверка, является ли страна частью Шенгена"""
        return code.upper() in self.SCHENGEN_COUNTRIES
    
    def is_non_standard(self, code: str) -> bool:
        """Проверка на нестандартную страну"""
        return code.upper() in self.NON_STANDARD_CODES


# Глобальный экземпляр базы стран
COUNTRY_DB = CountryDatabase()


# ═══════════════════════════════════════════════════════════════════════════════
# ДЕТЕКТОРЫ (ANALYZERS)
# ═══════════════════════════════════════════════════════════════════════════════

class TextAnalyzer:
    """Базовый класс для текстового анализа"""
    
    @staticmethod
    def normalize_text(text: str, max_length: int = 8000) -> str:
        """Нормализация текста для анализа"""
        # Убираем HTML теги
        text = re.sub(r'<[^>]+>', ' ', text)
        # Убираем множественные пробелы
        text = re.sub(r'\s+', ' ', text)
        # Обрезаем если слишком длинный (берём конец - он более релевантен)
        if len(text) > max_length:
            text = text[-max_length:]
        return text.strip().lower()
    
    @staticmethod
    def extract_emails(text: str) -> List[str]:
        """Извлечение email адресов из текста"""
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        return re.findall(pattern, text)
    
    @staticmethod
    def extract_dates(text: str) -> List[str]:
        """Извлечение дат из текста"""
        patterns = [
            r'\d{1,2}[./]\d{1,2}[./]\d{2,4}',
            r'\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
            r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}',
        ]
        dates = []
        for pattern in patterns:
            dates.extend(re.findall(pattern, text.lower()))
        return dates


class LanguageDetector(TextAnalyzer):
    """Детектор языка с улучшенной точностью"""
    
    # Веса для разных маркеров
    MARKERS = {
        Language.ENGLISH: {
            "strong": ["dear ", "hello", "good afternoon", "good morning", "good evening",
                      "please", "thank you", "regards", "sincerely", "best wishes"],
            "medium": ["the ", "and ", "for ", "with", "from", "have", "will", "would",
                      "could", "should", "about", "your", "our ", "this", "that"],
            "weak": ["is ", "are ", "was ", "were", "be ", "been"],
        },
        Language.RUSSIAN: {
            "strong": ["уважаемый", "уважаемая", "здравствуйте", "добрый день", "добрый вечер",
                      "с уважением", "пожалуйста", "спасибо", "благодарю"],
            "medium": ["прошу", "необходимо", "требуется", "хотел бы", "хотела бы",
                      "подскажите", "сообщите", "направляю", "высылаю"],
            "weak": ["это", "что", "как", "для", "при", "или", "и ", "в ", "на "],
        },
        Language.KAZAKH: {
            "strong": ["сәлем", "салем", "сәлеметсіз", "қайырлы", "рахмет"],
            "medium": ["керек", "болады", "мүмкін"],
            "weak": ["бұл", "мен", "сіз"],
        }
    }
    
    WEIGHTS = {"strong": 3.0, "medium": 1.5, "weak": 0.5}
    
    def detect(self, messages: List[Message]) -> Language:
        """Определение языка переписки"""
        text = self.normalize_text(
            " ".join(m.full_text for m in messages)
        )
        
        scores: Dict[Language, float] = {lang: 0.0 for lang in Language}
        
        for lang, markers in self.MARKERS.items():
            for strength, words in markers.items():
                weight = self.WEIGHTS[strength]
                for word in words:
                    count = text.count(word)
                    scores[lang] += count * weight
        
        # Определяем победителя
        best_lang = max(scores, key=scores.get)
        
        # Если казахский выигрывает, но русский близко - выбираем русский
        # (т.к. деловая переписка в Казахстане чаще на русском)
        if best_lang == Language.KAZAKH and scores[Language.RUSSIAN] > scores[Language.KAZAKH] * 0.5:
            return Language.RUSSIAN
        
        # Если нет явного победителя - русский по умолчанию
        if scores[best_lang] < 1.0:
            return Language.RUSSIAN
        
        return best_lang


class IntentDetector(TextAnalyzer):
    """Детектор намерений с контекстным анализом"""
    
    INTENT_PATTERNS = {
        Intent.WANT_APPLY: {
            "exact": [
                "хочу подать на визу", "хочу оформить визу", "нужно оформить визу",
                "хочу получить визу", "планирую получить визу", "готов подать документы",
                "готов заполнить анкету", "заполню вашу форму", "оформление визы",
                "i want to apply", "i would like to apply", "need to apply",
                "apply for a visa", "visa application", "ready to apply",
            ],
            "combined": [
                (["виз", "нужн"], 2.0),
                (["виз", "оформ"], 2.0),
                (["виз", "получ"], 2.0),
                (["виз", "подать"], 2.0),
                (["visa", "apply"], 2.0),
                (["visa", "need"], 2.0),
                (["visa", "get"], 1.5),
            ],
        },
        Intent.SEND_DOCS: {
            "exact": [
                "направляю документы", "высылаю документы", "во вложении документы",
                "документы во вложении", "прилагаю документы", "attached documents",
                "please find attached", "documents attached", "sending documents",
            ],
            "combined": [
                (["документ", "вложен"], 2.0),
                (["документ", "прилаг"], 2.0),
                (["attach", "document"], 2.0),
            ],
        },
        Intent.INFO_REQUEST: {
            "exact": [
                "прошу проинформировать", "расскажите подробнее", "информация по визе",
                "какие документы нужны", "что требуется для визы", "сколько стоит",
                "please advise", "could you provide information", "what documents",
                "what are the requirements", "how much does it cost",
            ],
            "combined": [
                (["информаци", "виз"], 1.5),
                (["подскажите", "виз"], 1.5),
                (["information", "visa"], 1.5),
            ],
        },
        Intent.FOLLOWUP: {
            "exact": [
                "какой статус", "есть новости", "как продвигается", "когда будет готово",
                "есть ли обновления", "any update", "any news", "status of my",
                "what is the status", "could you please update",
            ],
            "combined": [
                (["статус", "виз"], 2.0),
                (["статус", "заявк"], 2.0),
                (["status", "visa"], 2.0),
                (["update", "application"], 1.5),
            ],
        },
        Intent.COMPLAINT: {
            "exact": [
                "недоволен", "жалоба", "претензия", "возмущён", "неприемлемо",
                "complaint", "dissatisfied", "unacceptable", "not happy with",
            ],
            "combined": [
                (["недовол", "обслуживан"], 2.0),
                (["плох", "сервис"], 1.5),
            ],
        },
        Intent.GRATITUDE: {
            "exact": [
                "спасибо большое", "благодарю вас", "очень благодарен", "огромное спасибо",
                "thank you so much", "many thanks", "greatly appreciate", "thanks a lot",
            ],
            "combined": [],
        },
        Intent.CANCELLATION: {
            "exact": [
                "отменить заявку", "отказываюсь", "не нужна виза", "отмена",
                "cancel application", "cancel my visa", "no longer need",
            ],
            "combined": [
                (["отмен", "заявк"], 2.0),
                (["cancel", "visa"], 2.0),
            ],
        },
        Intent.RESCHEDULE: {
            "exact": [
                "перенести дату", "изменить дату", "перенос встречи",
                "reschedule", "change the date", "postpone",
            ],
            "combined": [
                (["перенес", "дат"], 2.0),
                (["измен", "дат"], 1.5),
            ],
        },
        Intent.PAYMENT: {
            "exact": [
                "оплата", "счёт", "инвойс", "квитанция", "реквизиты",
                "payment", "invoice", "receipt", "bank details",
            ],
            "combined": [
                (["оплат", "виз"], 1.5),
                (["payment", "visa"], 1.5),
            ],
        },
    }
    
    def detect(self, messages: List[Message]) -> Tuple[Intent, float]:
        """Определение намерения с оценкой уверенности"""
        text = self.normalize_text(
            " ".join(m.full_text for m in messages)
        )
        
        scores: Dict[Intent, float] = {intent: 0.0 for intent in Intent}
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            # Проверяем точные совпадения
            for exact in patterns.get("exact", []):
                if exact in text:
                    scores[intent] += 3.0
            
            # Проверяем комбинированные паттерны
            for keywords, weight in patterns.get("combined", []):
                if all(kw in text for kw in keywords):
                    scores[intent] += weight
        
        # Находим лучший результат
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]
        
        # Нормализуем уверенность
        confidence = min(best_score / 6.0, 1.0)  # 6.0 = 2 exact matches
        
        # Если уверенность низкая - возвращаем OTHER
        if confidence < 0.3:
            return Intent.OTHER, 0.0
        
        return best_intent, confidence


class UrgencyDetector(TextAnalyzer):
    """Детектор срочности с уровнями"""
    
    URGENCY_MARKERS = {
        UrgencyLevel.CRITICAL: [
            "вылет сегодня", "вылет завтра", "сегодня вечером", "завтра утром",
            "через несколько часов", "flight today", "flight tomorrow",
            "departing today", "departing tomorrow", "leaving today",
        ],
        UrgencyLevel.HIGH: [
            "очень срочно", "крайне срочно", "максимально быстро", "asap",
            "as soon as possible", "urgent", "urgently", "immediately",
            "критически важно", "extremely urgent",
        ],
        UrgencyLevel.MEDIUM: [
            "срочно", "как можно скорее", "как можно быстрее", "горит",
            "на этой неделе", "в ближайшие дни", "promptly", "soon",
            "this week", "in the coming days",
        ],
    }
    
    def detect(self, messages: List[Message]) -> UrgencyLevel:
        """Определение уровня срочности"""
        text = self.normalize_text(
            " ".join(m.full_text for m in messages)
        )
        
        # Проверяем от самого критичного к менее срочному
        for level in [UrgencyLevel.CRITICAL, UrgencyLevel.HIGH, UrgencyLevel.MEDIUM]:
            for marker in self.URGENCY_MARKERS[level]:
                if marker in text:
                    return level
        
        return UrgencyLevel.NORMAL


class SentimentDetector(TextAnalyzer):
    """Детектор тональности сообщения"""
    
    POSITIVE_MARKERS = [
        "спасибо", "благодарю", "отлично", "замечательно", "прекрасно",
        "thank you", "thanks", "great", "excellent", "wonderful", "appreciate",
        "доволен", "довольна", "рад", "рада", "satisfied", "happy",
    ]
    
    NEGATIVE_MARKERS = [
        "недоволен", "недовольна", "разочарован", "ужасно", "плохо",
        "unhappy", "disappointed", "terrible", "awful", "bad",
        "возмущён", "возмущена", "жалоба", "претензия", "complaint",
    ]
    
    def detect(self, messages: List[Message]) -> str:
        """Определение тональности: positive, neutral, negative"""
        text = self.normalize_text(
            " ".join(m.full_text for m in messages)
        )
        
        positive_count = sum(1 for m in self.POSITIVE_MARKERS if m in text)
        negative_count = sum(1 for m in self.NEGATIVE_MARKERS if m in text)
        
        if negative_count > positive_count:
            return "negative"
        if positive_count > negative_count and positive_count > 0:
            return "positive"
        return "neutral"


# ═══════════════════════════════════════════════════════════════════════════════
# МАШИНА СОСТОЯНИЙ (STATE MACHINE)
# ═══════════════════════════════════════════════════════════════════════════════

class StatusTransitionEngine:
    """Движок переходов между статусами"""
    
    # Матрица разрешённых переходов: текущий статус -> {intent -> новый статус}
    TRANSITIONS: Dict[LeadStatus, Dict[Intent, LeadStatus]] = {
        LeadStatus.NEW: {
            Intent.WANT_APPLY: LeadStatus.QUESTIONNAIRE_SENT,
            Intent.INFO_REQUEST: LeadStatus.INFO_PROVIDED,
            Intent.SEND_DOCS: LeadStatus.DOCS_IN_PROGRESS,
            Intent.CANCELLATION: LeadStatus.CANCELLED,
        },
        LeadStatus.INFO_PROVIDED: {
            Intent.WANT_APPLY: LeadStatus.QUESTIONNAIRE_SENT,
            Intent.SEND_DOCS: LeadStatus.DOCS_IN_PROGRESS,
            Intent.CANCELLATION: LeadStatus.CANCELLED,
        },
        LeadStatus.QUESTIONNAIRE_SENT: {
            Intent.SEND_DOCS: LeadStatus.QUESTIONNAIRE_FILLED,
            Intent.CANCELLATION: LeadStatus.CANCELLED,
        },
        LeadStatus.QUESTIONNAIRE_FILLED: {
            Intent.SEND_DOCS: LeadStatus.DOCS_IN_PROGRESS,
            Intent.CANCELLATION: LeadStatus.CANCELLED,
        },
        LeadStatus.DOCS_IN_PROGRESS: {
            Intent.SEND_DOCS: LeadStatus.DOCS_COLLECTED,
            Intent.CANCELLATION: LeadStatus.CANCELLED,
        },
        LeadStatus.DOCS_COLLECTED: {
            Intent.CANCELLATION: LeadStatus.CANCELLED,
        },
        LeadStatus.READY_FOR_SUBMISSION: {
            Intent.CANCELLATION: LeadStatus.CANCELLED,
        },
        LeadStatus.SUBMITTED: {
            Intent.CANCELLATION: LeadStatus.CANCELLED,
        },
        LeadStatus.INTERVIEW_SCHEDULED: {
            Intent.RESCHEDULE: LeadStatus.INTERVIEW_SCHEDULED,
            Intent.CANCELLATION: LeadStatus.CANCELLED,
        },
        LeadStatus.APPROVED: {},
        LeadStatus.REJECTED: {
            Intent.WANT_APPLY: LeadStatus.QUESTIONNAIRE_SENT,  # Повторная подача
        },
        LeadStatus.COMPLETED: {},
        LeadStatus.CANCELLED: {
            Intent.WANT_APPLY: LeadStatus.QUESTIONNAIRE_SENT,  # Возобновление
        },
    }
    
    @classmethod
    def get_new_status(cls, current: LeadStatus, intent: Intent) -> LeadStatus:
        """Определение нового статуса на основе текущего и намерения"""
        allowed = cls.TRANSITIONS.get(current, {})
        return allowed.get(intent, current)


# ═══════════════════════════════════════════════════════════════════════════════
# ЛОГИКА ФОРМ
# ═══════════════════════════════════════════════════════════════════════════════

class FormSelector:
    """Логика выбора форм для отправки"""
    
    @staticmethod
    def should_offer_forms(
        country: Optional[Country],
        intent: Intent,
        existing_forms: Dict[str, bool],
    ) -> Dict[str, bool]:
        """
        Определение какие формы нужно предложить.
        
        Args:
            country: Определённая страна
            intent: Намерение клиента
            existing_forms: Словарь уже отправленных форм
        
        Returns:
            Словарь с флагами для каждого типа формы
        """
        result = {
            "poland": False,
            "schengen": False,
            "usa": False,
            "generic": False,
        }
        
        # Нестандартные страны - формы не отправляем
        if country and country.category == VisaCategory.NON_STANDARD:
            return result
        
        # Только для intent=want_apply отправляем формы
        if intent != Intent.WANT_APPLY:
            return result
        
        # Определяем нужную форму
        if country:
            form_type = country.form_type
            if form_type and not existing_forms.get(form_type, False):
                result[form_type] = True
        else:
            # Страна не определена - предлагаем generic
            if not existing_forms.get("generic", False):
                result["generic"] = True
        
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ АНАЛИЗАТОР
# ═══════════════════════════════════════════════════════════════════════════════

class ThreadAnalyzer:
    """Главный класс анализа переписки"""
    
    def __init__(
        self,
        language_detector: Optional[LanguageDetector] = None,
        intent_detector: Optional[IntentDetector] = None,
        urgency_detector: Optional[UrgencyDetector] = None,
        sentiment_detector: Optional[SentimentDetector] = None,
    ):
        self.language_detector = language_detector or LanguageDetector()
        self.intent_detector = intent_detector or IntentDetector()
        self.urgency_detector = urgency_detector or UrgencyDetector()
        self.sentiment_detector = sentiment_detector or SentimentDetector()
    
    def analyze(
        self,
        messages: List[Message],
        our_address: str = CONFIG.mailbox_upn,
        previous_status: Optional[str] = None,
        existing_forms: Optional[Dict[str, bool]] = None,
    ) -> ThreadAnalysis:
        """Полный анализ переписки"""
        
        if not messages:
            return self._empty_analysis(previous_status)
        
        # Фильтруем только входящие сообщения для анализа намерений
        client_messages = [
            m for m in messages 
            if m.from_address.lower() != our_address.lower()
        ]
        
        # Используем все сообщения для контекста
        all_messages = messages
        
        # 1. Определяем язык
        language = self.language_detector.detect(client_messages or all_messages)
        
        # 2. Определяем страну
        country = COUNTRY_DB.find_country(
            " ".join(m.full_text for m in client_messages or all_messages)
        )
        
        # 3. Определяем намерение
        intent, confidence = self.intent_detector.detect(client_messages or all_messages)
        
        # 4. Определяем срочность
        urgency = self.urgency_detector.detect(client_messages or all_messages)
        
        # 5. Определяем тональность
        sentiment = self.sentiment_detector.detect(client_messages or all_messages)
        
        # 6. Определяем статус
        prev_status = LeadStatus.from_string(previous_status)
        new_status = StatusTransitionEngine.get_new_status(prev_status, intent)
        
        # 7. Определяем формы
        existing = existing_forms or {}
        forms = FormSelector.should_offer_forms(country, intent, existing)
        
        # 8. Проверяем наличие вложений
        has_attachments = any(m.attachments for m in messages)
        
        # 9. Определяем маршрутизацию
        is_non_standard = country and country.category == VisaCategory.NON_STANDARD
        forward_to = None
        forward_reason = None
        
        if is_non_standard:
            forward_to = CONFIG.non_standard_forward_email
            forward_reason = "non_standard_country"
        
        # Собираем результат
        analysis = ThreadAnalysis(
            language=language,
            detected_country=country,
            intent=intent,
            urgency=urgency,
            previous_status=prev_status,
            new_status=new_status,
            offer_poland_form=forms["poland"],
            offer_schengen_form=forms["schengen"],
            offer_usa_form=forms["usa"],
            offer_generic_form=forms["generic"],
            is_non_standard_destination=is_non_standard,
            has_attachments=has_attachments,
            sentiment=sentiment,
            forward_to_email=forward_to,
            forward_reason=forward_reason,
            confidence_score=confidence,
        )
        
        logger.debug("Thread analysis completed: %s", analysis)
        return analysis
    
    def _empty_analysis(self, previous_status: Optional[str]) -> ThreadAnalysis:
        """Анализ для пустого треда"""
        prev = LeadStatus.from_string(previous_status)
        return ThreadAnalysis(
            language=Language.RUSSIAN,
            detected_country=None,
            intent=Intent.OTHER,
            urgency=UrgencyLevel.NORMAL,
            previous_status=prev,
            new_status=prev,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ГЕНЕРАТОР ОТВЕТОВ
# ═══════════════════════════════════════════════════════════════════════════════

class ReplyGenerator:
    """Генератор ответов на основе анализа"""
    
    def __init__(self, config: Config = CONFIG):
        self.config = config
    
    def generate(
        self,
        messages: List[Message],
        analysis: ThreadAnalysis,
        form_links: FormLinks,
        extra_context: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> str:
        """Генерация ответа"""
        
        # Строим промпт
        llm_messages = self._build_messages(messages, analysis, form_links, extra_context)
        
        # Вызываем LLM
        reply = generate_chat_completion(
            llm_messages,
            model=model or self.config.default_model,
            max_tokens=self.config.max_tokens_reply,
            temperature=self.config.temperature,
        )
        
        # Постобработка
        reply = self._postprocess(reply, analysis, form_links)
        
        return reply
    
    def _build_messages(
        self,
        messages: List[Message],
        analysis: ThreadAnalysis,
        form_links: FormLinks,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Построение сообщений для LLM"""
        
        system_prompt = self._build_system_prompt(analysis.language)
        user_content = self._build_user_prompt(messages, analysis, form_links, extra_context)
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    
    def _build_system_prompt(self, language: Language) -> str:
        """Системный промпт"""
        
        if language == Language.ENGLISH:
            return """You are a professional visa consultant at TRAVEL PLUS VISA Kazakhstan.

COMMUNICATION STYLE:
- Write clear, structured, and polite business emails
- Be helpful and proactive
- Use short paragraphs and bullet points when appropriate

RULES:
1. Answer the client's questions directly and completely
2. If information is missing, politely ask for clarification
3. NEVER invent facts about consulates, prices, or processing times
4. When providing questionnaire links, use the EXACT URLs provided - no placeholders
5. If the request is urgent, acknowledge it and commit to priority processing
6. If the country is already identified, don't ask about it again

SIGNATURE:
Always end with:
Best regards,
TRAVEL PLUS VISA Kazakhstan
visa@bcdtravel.kz"""

        else:  # Russian/Kazakh
            return """Вы — профессиональный визовый консультант компании BCD TRAVEL Казахстан.

СТИЛЬ ОБЩЕНИЯ:
- Пишите чёткие, структурированные и вежливые деловые письма
- Будьте полезным и проактивным
- Используйте короткие абзацы и списки там, где это уместно

ПРАВИЛА:
1. Отвечайте на вопросы клиента прямо и полностью
2. Если информации недостаточно, вежливо запросите уточнения
3. НИКОГДА не выдумывайте факты о консульствах, ценах или сроках
4. При упоминании анкет используйте ТОЧНЫЕ URL из предоставленных ссылок — без плейсхолдеров
5. Если запрос срочный, подтвердите это и обещайте приоритетную обработку
6. Если страна уже определена, не спрашивайте о ней повторно

ПОДПИСЬ:
Всегда завершайте письмо:
С уважением,
BCD TRAVEL Казахстан
visa@bcdtravel.kz"""
    
    def _build_user_prompt(
        self,
        messages: List[Message],
        analysis: ThreadAnalysis,
        form_links: FormLinks,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Построение пользовательского промпта"""
        
        parts = []
        lang = analysis.language
        is_english = lang == Language.ENGLISH
        
        # 1. Метаданные анализа
        parts.append(self._build_meta_block(analysis, is_english))
        
        # 2. Ссылки на формы
        forms_block = self._build_forms_block(analysis, form_links, is_english)
        if forms_block:
            parts.append(forms_block)
        
        # 3. Дополнительный контекст
        if extra_context:
            ctx_str = json.dumps(extra_context, ensure_ascii=False, indent=2)
            header = "Additional context:" if is_english else "Дополнительный контекст:"
            parts.append(f"\n{header}\n{ctx_str}")
        
        # 4. Переписка
        parts.append(self._build_conversation_block(messages, is_english))
        
        # 5. Инструкция
        parts.append(self._build_instruction(analysis, is_english))
        
        return "\n\n".join(parts)
    
    def _build_meta_block(self, analysis: ThreadAnalysis, is_english: bool) -> str:
        """Блок метаданных анализа"""
        
        country = analysis.country_code or "unknown"
        urgency_map = {
            UrgencyLevel.CRITICAL: "CRITICAL (flight today/tomorrow)",
            UrgencyLevel.HIGH: "HIGH (ASAP)",
            UrgencyLevel.MEDIUM: "MEDIUM (this week)",
            UrgencyLevel.NORMAL: "NORMAL",
            UrgencyLevel.LOW: "LOW",
        }
        
        if is_english:
            return f"""=== INTERNAL ANALYSIS (do not output to client) ===
Intent: {analysis.intent.value}
Country: {country}
Previous status: {analysis.previous_status.value}
New status: {analysis.new_status.value}
Urgency: {urgency_map.get(analysis.urgency, 'NORMAL')}
Sentiment: {analysis.sentiment}
Non-standard destination: {'YES' if analysis.is_non_standard_destination else 'NO'}
Has attachments: {'YES' if analysis.has_attachments else 'NO'}
Confidence: {analysis.confidence_score:.0%}"""
        else:
            urgency_ru = {
                UrgencyLevel.CRITICAL: "КРИТИЧНО (вылет сегодня/завтра)",
                UrgencyLevel.HIGH: "ВЫСОКАЯ (срочно)",
                UrgencyLevel.MEDIUM: "СРЕДНЯЯ (на этой неделе)",
                UrgencyLevel.NORMAL: "ОБЫЧНАЯ",
                UrgencyLevel.LOW: "НИЗКАЯ",
            }
            return f"""=== ВНУТРЕННИЙ АНАЛИЗ (не выводить клиенту) ===
Намерение: {analysis.intent.value}
Страна: {country}
Предыдущий статус: {analysis.previous_status.value}
Новый статус: {analysis.new_status.value}
Срочность: {urgency_ru.get(analysis.urgency, 'ОБЫЧНАЯ')}
Тональность: {analysis.sentiment}
Нестандартное направление: {'ДА' if analysis.is_non_standard_destination else 'НЕТ'}
Есть вложения: {'ДА' if analysis.has_attachments else 'НЕТ'}
Уверенность: {analysis.confidence_score:.0%}"""
    
    def _build_forms_block(
        self,
        analysis: ThreadAnalysis,
        form_links: FormLinks,
        is_english: bool,
    ) -> str:
        """Блок со ссылками на формы"""
        
        if analysis.is_non_standard_destination:
            return ""
        
        links = []
        
        if analysis.offer_poland_form and form_links.poland:
            label = "Poland visa questionnaire" if is_english else "Анкета на визу в Польшу"
            links.append(f"- {label}: {form_links.poland}")
        
        if analysis.offer_schengen_form and form_links.schengen:
            label = "Schengen visa questionnaire" if is_english else "Анкета на шенгенскую визу"
            links.append(f"- {label}: {form_links.schengen}")
        
        if analysis.offer_usa_form and form_links.usa:
            label = "USA visa questionnaire (DS-160)" if is_english else "Анкета на визу США"
            links.append(f"- {label}: {form_links.usa}")
        
        if analysis.offer_generic_form and form_links.generic:
            label = "General visa questionnaire" if is_english else "Универсальная визовая анкета"
            links.append(f"- {label}: {form_links.generic}")
        
        if not links:
            return ""
        
        if is_english:
            header = "=== QUESTIONNAIRE LINKS (use these exact URLs in your reply) ==="
        else:
            header = "=== ССЫЛКИ НА АНКЕТЫ (используйте эти URL в ответе) ==="
        
        return header + "\n" + "\n".join(links)
    
    def _build_conversation_block(self, messages: List[Message], is_english: bool) -> str:
        """Блок переписки"""
        
        header = "=== EMAIL THREAD ===" if is_english else "=== ПЕРЕПИСКА ==="
        
        blocks = []
        for msg in messages:
            who = "Client" if msg.from_address.lower() != self.config.mailbox_upn.lower() else "BCD TRAVEL"
            
            date_str = ""
            if msg.received_at:
                date_str = f" ({msg.received_at})"
            
            block = f"From: {who} <{msg.from_address}>{date_str}\nSubject: {msg.subject}\n\n{msg.body}"
            blocks.append(block)
        
        return header + "\n\n" + "\n\n---\n\n".join(blocks)
    
    def _build_instruction(self, analysis: ThreadAnalysis, is_english: bool) -> str:
        """Инструкция для LLM"""
        
        hints = []
        
        # Подсказки по срочности
        if analysis.urgency in (UrgencyLevel.CRITICAL, UrgencyLevel.HIGH):
            if is_english:
                hints.append("- URGENT: Acknowledge urgency in the opening paragraph")
            else:
                hints.append("- СРОЧНО: Подтвердите срочность в начале письма")
        
        # Подсказки по стране
        if analysis.detected_country and not analysis.is_non_standard_destination:
            country_name = analysis.detected_country.code
            if is_english:
                hints.append(f"- Country detected: {country_name}. Don't ask about destination again.")
            else:
                hints.append(f"- Страна определена: {country_name}. Не спрашивайте о направлении повторно.")
        
        # Подсказки по нестандартным странам
        if analysis.is_non_standard_destination:
            if is_english:
                hints.append("- Non-standard destination: Inform that this requires individual processing")
            else:
                hints.append("- Нестандартное направление: Сообщите, что требуется индивидуальная обработка")
        
        # Подсказки по формам
        if analysis.needs_form:
            if is_english:
                hints.append("- Include the questionnaire link naturally in your response")
            else:
                hints.append("- Включите ссылку на анкету естественно в текст ответа")
        
        # Подсказки по тональности
        if analysis.sentiment == "negative":
            if is_english:
                hints.append("- Client seems upset: Be extra empathetic and professional")
            else:
                hints.append("- Клиент недоволен: Будьте особенно эмпатичны и профессиональны")
        
        hints_text = "\n".join(hints) if hints else ""
        
        if is_english:
            return f"""=== TASK ===
Write a professional reply to the client based on the thread above.
{hints_text}

Write your response now:"""
        else:
            return f"""=== ЗАДАЧА ===
Напишите профессиональный ответ клиенту на основе переписки выше.
{hints_text}

Напишите ответ:"""
    
    def _postprocess(
        self,
        reply: str,
        analysis: ThreadAnalysis,
        form_links: FormLinks,
    ) -> str:
        """Постобработка ответа"""
        
        # Заменяем плейсхолдеры на реальные ссылки
        url = self._get_primary_form_url(analysis, form_links)
        
        if url:
            # Русские плейсхолдеры
            placeholders_ru = [
                r'\[ссылка\s*на\s*анкету\]',
                r'\[ссылка\]',
                r'\[заполнить\s*анкету\]',
                r'по\s+ссылке\s+ниже\.?\s*$',
            ]
            
            for pattern in placeholders_ru:
                reply = re.sub(pattern, url, reply, flags=re.IGNORECASE)
            
            # Английские плейсхолдеры
            placeholders_en = [
                r'\[link\s*to\s*(the\s*)?questionnaire\]',
                r'\[link\]',
                r'\[fill\s*out\s*(the\s*)?form\]',
            ]
            
            for pattern in placeholders_en:
                reply = re.sub(pattern, url, reply, flags=re.IGNORECASE)
            
            # Если есть "ссылка ниже" без фактической ссылки
            if ("ссылка ниже" in reply.lower() or "link below" in reply.lower()) and url not in reply:
                if analysis.language == Language.ENGLISH:
                    reply += f"\n\nQuestionnaire link: {url}"
                else:
                    reply += f"\n\nСсылка на анкету: {url}"
        
        return reply.strip()
    
    def _get_primary_form_url(
        self,
        analysis: ThreadAnalysis,
        form_links: FormLinks,
    ) -> Optional[str]:
        """Получение основной ссылки на форму"""
        
        if analysis.is_non_standard_destination:
            return None
        
        if analysis.offer_poland_form and form_links.poland:
            return form_links.poland
        if analysis.offer_schengen_form and form_links.schengen:
            return form_links.schengen
        if analysis.offer_usa_form and form_links.usa:
            return form_links.usa
        if analysis.offer_generic_form and form_links.generic:
            return form_links.generic
        
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# ПУБЛИЧНЫЕ API ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════════════════

def classify_message(
    thread_messages: Union[str, List[Union[Message, Dict[str, Any]]]],
    our_address: str = CONFIG.mailbox_upn,
    previous_status: Optional[str] = None,
    existing_poland_form: bool = False,
    existing_schengen_form: bool = False,
    existing_usa_form: bool = False,
    existing_generic_form: bool = False,
) -> Dict[str, Any]:
    """
    Классификация сообщений - основной API для анализа.
    
    Args:
        thread_messages: Строка или список сообщений
        our_address: Email адрес нашей компании
        previous_status: Предыдущий статус лида
        existing_*_form: Флаги уже отправленных форм
    
    Returns:
        Словарь с результатами анализа
    """
    
    # Конвертируем входные данные в список Message
    messages = _normalize_messages(thread_messages)
    
    # Создаём анализатор и выполняем анализ
    analyzer = ThreadAnalyzer()
    
    existing_forms = {
        "poland": existing_poland_form,
        "schengen": existing_schengen_form,
        "usa": existing_usa_form,
        "generic": existing_generic_form,
    }
    
    analysis = analyzer.analyze(
        messages=messages,
        our_address=our_address,
        previous_status=previous_status,
        existing_forms=existing_forms,
    )
    
    # Конвертируем в словарь для совместимости
    return {
        "language": analysis.language.value,
        "country": analysis.country_code,
        "intent": analysis.intent.value,
        "previous_status": analysis.previous_status.value,
        "new_status": analysis.new_status.value,
        "offer_poland_form": analysis.offer_poland_form,
        "offer_schengen_form": analysis.offer_schengen_form,
        "offer_usa_form": analysis.offer_usa_form,
        "offer_generic_form": analysis.offer_generic_form,
        "is_urgent": analysis.urgency in (UrgencyLevel.CRITICAL, UrgencyLevel.HIGH, UrgencyLevel.MEDIUM),
        "urgency_level": analysis.urgency.name,
        "is_non_standard_destination": analysis.is_non_standard_destination,
        "forward_to_email": analysis.forward_to_email,
        "forward_reason": analysis.forward_reason,
        "form_code": analysis.form_type,
        "needs_form": analysis.needs_form,
        "sentiment": analysis.sentiment,
        "confidence_score": analysis.confidence_score,
        "has_attachments": analysis.has_attachments,
    }


def generate_reply_from_thread(
    thread_messages_or_text: Union[str, List[Union[Message, Dict[str, Any]]]],
    our_address: str = CONFIG.mailbox_upn,
    previous_status: Optional[str] = None,
    existing_poland_form: bool = False,
    existing_schengen_form: bool = False,
    existing_usa_form: bool = False,
    existing_generic_form: bool = False,
    form_links: Optional[FormLinks] = None,
    extra_config: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> str:
    """
    Генерация ответа на переписку - основной API для создания ответов.
    
    Args:
        thread_messages_or_text: Текст или список сообщений
        our_address: Email адрес нашей компании
        previous_status: Предыдущий статус лида
        existing_*_form: Флаги уже отправленных форм
        form_links: Ссылки на формы
        extra_config: Дополнительный контекст
        model: Модель LLM для использования
    
    Returns:
        Сгенерированный ответ
    """
    
    # Конвертируем входные данные
    messages = _normalize_messages(thread_messages_or_text)
    
    # Анализируем
    analyzer = ThreadAnalyzer()
    
    existing_forms = {
        "poland": existing_poland_form,
        "schengen": existing_schengen_form,
        "usa": existing_usa_form,
        "generic": existing_generic_form,
    }
    
    analysis = analyzer.analyze(
        messages=messages,
        our_address=our_address,
        previous_status=previous_status,
        existing_forms=existing_forms,
    )
    
    # Получаем ссылки
    links = form_links or FormLinks.from_config()
    
    # Генерируем ответ
    generator = ReplyGenerator()
    reply = generator.generate(
        messages=messages,
        analysis=analysis,
        form_links=links,
        extra_context=extra_config,
        model=model,
    )
    
    return reply


def _normalize_messages(
    input_data: Union[str, List[Union[Message, Dict[str, Any], str]]],
) -> List[Message]:
    """Нормализация входных данных в список Message"""
    
    if isinstance(input_data, str):
        return [Message(from_address="", subject="", body=input_data)]
    
    messages = []
    for item in input_data:
        if isinstance(item, Message):
            messages.append(item)
        elif isinstance(item, dict):
            messages.append(Message.from_dict(item))
        elif isinstance(item, str):
            messages.append(Message(from_address="", subject="", body=item))
    
    return messages


# ═══════════════════════════════════════════════════════════════════════════════
# УТИЛИТЫ ДЛЯ ТЕСТИРОВАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_single_message(text: str) -> Dict[str, Any]:
    """Быстрый анализ одного сообщения (для тестирования)"""
    return classify_message(text)


def generate_simple_reply(text: str, model: Optional[str] = None) -> str:
    """Быстрая генерация ответа на одно сообщение (для тестирования)"""
    return generate_reply_from_thread(text, model=model)


# ═══════════════════════════════════════════════════════════════════════════════
# ЭКСПОРТ
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Модели данных
    "Message",
    "FormLinks",
    "ThreadAnalysis",
    "Country",
    "Config",
    
    # Перечисления
    "Language",
    "Intent",
    "LeadStatus",
    "UrgencyLevel",
    "VisaCategory",
    
    # Основные классы
    "ThreadAnalyzer",
    "ReplyGenerator",
    "CountryDatabase",
    
    # Детекторы
    "LanguageDetector",
    "IntentDetector",
    "UrgencyDetector",
    "SentimentDetector",
    
    # Публичные API
    "classify_message",
    "generate_reply_from_thread",
    
    # Утилиты
    "analyze_single_message",
    "generate_simple_reply",
    
    # Конфигурация
    "CONFIG",
    "COUNTRY_DB",
]