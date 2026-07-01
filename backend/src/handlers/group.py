from aiogram import Router
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import ChatMemberUpdated

group_router = Router()


@group_router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER)
)
async def bot_added_to_group(event: ChatMemberUpdated) -> None:
    title = event.chat.title or "este grupo"
    await event.answer(
        f"¡Gracias por añadirme a <b>{title}</b>! 🎉\n\n"
        "Escribe /stop para comenzar una partida."
    )
