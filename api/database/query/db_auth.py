from datetime import datetime, timezone
from typing import Optional, Dict
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession
from fastapi import HTTPException, status

class DBAuth:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["users"]

    async def _execute_in_transaction(self, operation, *args, **kwargs):
        """Execute an operation within a transaction"""
        async with await self.db.client.start_session() as session:
            async with session.start_transaction():
                try:
                    result = await operation(*args, **kwargs)
                    return result
                except Exception as e:
                    await session.abort_transaction()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Database operation failed: {str(e)}"
                    )

    async def find_user_by_email(self, email: str) -> Optional[Dict]:
        """Find a user by email"""
        return await self._execute_in_transaction(
            self.collection.find_one,
            {"email": email}
        )

    async def create_user(self, user_data: Dict) -> Dict:
        """Create a new user"""
        async def _create():
            user_data["created_at"] = datetime.now(timezone.utc)
            user_data["updated_at"] = datetime.now(timezone.utc)
            
            result = await self.collection.insert_one(user_data)
            user_data["id"] = str(result.inserted_id)
            return user_data

        return await self._execute_in_transaction(_create)

    async def update_last_login(self, user_id: str) -> None:
        """Update the last login time for a user"""
        async def _update():
            await self.collection.update_one(
                {"_id": user_id},
                {"$set": {"last_login": datetime.now(timezone.utc)}}
            )

        await self._execute_in_transaction(_update)

    async def check_email_exists(self, email: str) -> bool:
        """Check if an email already exists in the database"""
        existing_user = await self.find_user_by_email(email)
        return existing_user is not None
