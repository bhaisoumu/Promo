from motor.motor_asyncio import AsyncIOMotorClient
from config import config
import asyncio

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.sudo_collection = None
        self.settings_collection = None
        self.auto_broadcast_collection = None
        
    async def connect(self):
        self.client = AsyncIOMotorClient(config.MONGODB_URI)
        self.db = self.client[config.DATABASE_NAME]
        self.sudo_collection = self.db["sudo_users"]
        self.settings_collection = self.db["settings"]
        self.auto_broadcast_collection = self.db["auto_broadcast"]
        
        await self.sudo_collection.create_index("user_id", unique=True)
        await self.settings_collection.create_index("key", unique=True)
        
        await self.load_sudo_users()
        await self.load_settings()
        await self.load_dm_block()
        
    # --- Sudo Users ---
    async def load_sudo_users(self):
        sudo_users = []
        async for doc in self.sudo_collection.find():
            sudo_users.append(doc["user_id"])
        config.SUDO_USERS = sudo_users
        
    async def add_sudo_user(self, user_id: int):
        await self.sudo_collection.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id}},
            upsert=True
        )
        await self.load_sudo_users()
        
    async def remove_sudo_user(self, user_id: int):
        await self.sudo_collection.delete_one({"user_id": user_id})
        await self.load_sudo_users()
        
    # --- General Settings ---
    async def load_settings(self):
        settings = await self.settings_collection.find_one({"key": "settings"})
        if settings:
            config.DEFAULT_DELAY = settings.get("delay", 2)
            config.DEFAULT_MODE = settings.get("mode", "parallel")
            
    async def save_settings(self, delay: int = None, mode: str = None):
        settings = await self.settings_collection.find_one({"key": "settings"})
        if not settings:
            settings = {"key": "settings"}
        if delay is not None:
            settings["delay"] = delay
            config.DEFAULT_DELAY = delay
        if mode is not None:
            settings["mode"] = mode
            config.DEFAULT_MODE = mode
        await self.settings_collection.update_one(
            {"key": "settings"},
            {"$set": settings},
            upsert=True
        )
        
    # --- DM Block ---
    async def load_dm_block(self):
        doc = await self.settings_collection.find_one({"key": "dm_block"})
        config.AUTO_DM_BLOCK = doc.get("active", False) if doc else False
        
    async def save_dm_block(self, active: bool):
        await self.settings_collection.update_one(
            {"key": "dm_block"},
            {"$set": {"active": active}},
            upsert=True
        )
        config.AUTO_DM_BLOCK = active
        
    # --- Auto Broadcast ---
    async def get_auto_broadcast(self):
        return await self.auto_broadcast_collection.find_one({"key": "auto_broadcast"})
        
    async def save_auto_broadcast(self, interval: int, message_id: int, chat_id: int, active: bool = True):
        await self.auto_broadcast_collection.update_one(
            {"key": "auto_broadcast"},
            {"$set": {
                "interval": interval,
                "message_id": message_id,
                "chat_id": chat_id,
                "active": active,
                "updated_at": asyncio.get_event_loop().time()
            }},
            upsert=True
        )
        config.AUTO_BROADCAST_INTERVAL = interval
        config.AUTO_BROADCAST_ACTIVE = active
        
    async def disable_auto_broadcast(self):
        await self.auto_broadcast_collection.update_one(
            {"key": "auto_broadcast"},
            {"$set": {"active": False}}
        )
        config.AUTO_BROADCAST_ACTIVE = False

database = Database()
