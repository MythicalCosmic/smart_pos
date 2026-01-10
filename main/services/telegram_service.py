import requests
import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str
    timeout: int = 10
    max_retries: int = 3


class TelegramService:
    
    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"
    
    def __init__(self, config: TelegramConfig):
        self.config = config
        self._url = self.BASE_URL.format(token=config.bot_token)
    
    def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False
    ) -> tuple[bool, Optional[str]]:
        payload = {
            "chat_id": self.config.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification
        }
        
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = requests.post(
                    self._url,
                    json=payload,
                    timeout=self.config.timeout
                )
                
                if response.status_code == 200:
                    logger.info("Telegram message sent successfully")
                    return True, None
                
                error_msg = f"Telegram API error: {response.status_code} - {response.text}"
                logger.warning(f"Attempt {attempt}/{self.config.max_retries}: {error_msg}")
                
            except requests.exceptions.ConnectionError:
                error_msg = "No internet connection"
                logger.warning(f"Attempt {attempt}/{self.config.max_retries}: {error_msg}")
                
            except requests.exceptions.Timeout:
                error_msg = "Request timed out"
                logger.warning(f"Attempt {attempt}/{self.config.max_retries}: {error_msg}")
                
            except requests.exceptions.RequestException as e:
                error_msg = f"Request failed: {str(e)}"
                logger.warning(f"Attempt {attempt}/{self.config.max_retries}: {error_msg}")
        
        logger.error(f"Failed to send Telegram message after {self.config.max_retries} attempts")
        return False, error_msg
    
    def is_online(self) -> bool:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{self.config.bot_token}/getMe",
                timeout=5
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

DEFAULT_CONFIG = TelegramConfig(
    bot_token="8346442289:AAHusPm9aD_v-190cmD-XRApfFJ0UnXcrOQ",
    chat_id="6589960007"
)


def get_telegram_service(config: Optional[TelegramConfig] = None) -> TelegramService:
    return TelegramService(config or DEFAULT_CONFIG)