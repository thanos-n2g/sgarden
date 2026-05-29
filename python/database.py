"""MongoDB client and collection handles, plus index initialisation."""
from motor.motor_asyncio import AsyncIOMotorClient

from config import settings

client = AsyncIOMotorClient(settings.database_url)

_raw_path = settings.database_url.rsplit("/", 1)[-1] if "/" in settings.database_url else "sgarden"
db_name = _raw_path.split("?")[0] or "sgarden"
db = client[db_name]

users_collection = db["users"]
products_collection = db["products"]
orders_collection = db["orders"]


async def init_indexes():
    """Create unique indexes on startup."""
    await users_collection.create_index("username", unique=True)
    await users_collection.create_index("email", unique=True)
