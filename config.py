import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    API_ID = int(os.getenv("API_ID", "123456"))
    API_HASH = os.getenv("API_HASH", "your_api_hash_here")
    PHONE = os.getenv("PHONE", "+1234567890")
    OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
    
    # MongoDB
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "userbot")
    
    # Default Settings
    DEFAULT_DELAY = int(os.getenv("DEFAULT_DELAY", "2"))
    DEFAULT_MODE = os.getenv("DEFAULT_MODE", "parallel")
    
    # Log Group (for forwarding errors/logs)
    LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0"))   # 0 means disabled
    
    # Runtime settings (loaded from DB)
    SUDO_USERS = []
    AUTO_BROADCAST_INTERVAL = 0
    AUTO_BROADCAST_ACTIVE = False
    AUTO_DM_BLOCK = False

config = Config()
