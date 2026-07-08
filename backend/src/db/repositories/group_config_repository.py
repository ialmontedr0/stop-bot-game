from typing import Optional

from sqlalchemy import select

from src.db.models import GroupConfig


class GroupConfigRepository:
    def __init__(self, session):
        self.session = session

    async def get_by_group(self, group_chat_id: int) -> Optional[GroupConfig]:
        stmt = select(GroupConfig).where(GroupConfig.group_chat_id == group_chat_id)
        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def get_or_create(self, group_chat_id: int) -> GroupConfig:
        config = await self.get_by_group(group_chat_id)
        if config is None:
            config = GroupConfig(group_chat_id=group_chat_id)
            self.session.add(config)
            await self.session.flush()
            await self.session.refresh(config)
        return config
