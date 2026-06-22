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
    
    # Sudo Users (loaded from DB)
    SUDO_USERS = []
    
    # Auto Broadcast (loaded from DB)
    AUTO_BROADCAST_INTERVAL = 0
    AUTO_BROADCAST_ACTIVE = False
    
    # DM Block (loaded from DB)
    AUTO_DM_BLOCK = False

config = Config()
