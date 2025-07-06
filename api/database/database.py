# Created by: thongnt
from typing import Any, Callable, Coroutine
import contextlib
import ssl
from typing import Any, AsyncIterator
import motor.motor_asyncio
from pymongo.errors import ConnectionFailure
from api.constant.config import MONGODB_CONNECTION_URL

client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_CONNECTION_URL)
db = client.get_database()  # Get the default database


class MongoDBSessionManager:
    def __init__(self, connection_url: str):
        """Initialize MongoDB connection manager.
        
        Args:
            connection_url: MongoDB connection string
        """
        client_kwargs = {}
            
        self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_url, **client_kwargs)
        self.db = self.client.get_default_database()
        
    async def close(self):
        """Close the MongoDB client connection."""
        if self.client is None:
            raise Exception("MongoDBSessionManager is not initialized")
        
        self.client.close()
        self.client = None
        self.db = None
        
    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[motor.motor_asyncio.AsyncIOMotorClientSession]:
        """Create and yield a MongoDB session."""
        if self.client is None:
            raise Exception("MongoDBSessionManager is not initialized")
        
        session = await self.client.start_session()
        try:
            yield session
        except Exception as e:
            await session.abort_transaction()
            raise e
        finally:
            await session.end_session()
    
    async def create_collections(self, collections: list[str]):
        """Create collections if they don't exist.
        
        Args:
            collections: List of collection names to create
        """
        existing_collections = await self.db.list_collection_names()
        for collection in collections:
            if collection not in existing_collections:
                await self.db.create_collection(collection)
    
    async def run_with_session(
        self, 
        operation: Callable[[motor.motor_asyncio.AsyncIOMotorClientSession, str, Any], Coroutine], 
        session_id: str, 
        *args: Any
    ) -> Any:
        """Execute a database operation with its own session.
        
        Args:
            operation: Async function that takes (session, session_id, *args) as parameters
            session_id: Session ID to pass to the operation
            args: Additional arguments to pass to the operation
            
        Returns:
            Result from the operation
        """
        async with await self.client.start_session() as session:
            try:
                async with session.start_transaction():
                    result = await operation(session, session_id, *args)
                    return result
            except Exception as e:
                print(f"Error in run_with_session: {e}")
                raise e

# Initialize MongoDB session manager
session_manager = MongoDBSessionManager(MONGODB_CONNECTION_URL)

async def get_db():
    """Get MongoDB client session."""
    # async with session_manager.session() as session:
    #     yield session
    try:
        yield db  # Yield the database session (Motor client)
    finally:
        pass


async def run_with_session(
    operation: Callable[[motor.motor_asyncio.AsyncIOMotorClientSession, str, Any], Coroutine],
    session_id: str,
    *args: Any
) -> Any:
    """Run operation with MongoDB session."""
    return await session_manager.run_with_session(operation, session_id, *args)

# Helper function to get a specific collection
def get_collection(collection_name: str):
    """Get a MongoDB collection by name."""
    return session_manager.db[collection_name]
    