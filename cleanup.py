import asyncio
from datetime import datetime, timedelta
from storage.memory import active_events, memory  # Исправлен импорт

EVENT_EXPIRY_DAYS = 30  # Сколько дней храним информацию о сообщениях событий

async def cleanup_events_and_members(bot):
    """
    Мультисерверная версия:
    - Удаляет информацию о событиях (active_events), если событие прошло более месяца назад или сообщение удалено.
    - Удаляет из пресетов участников, покинувших сервер.
    - Удаляет user_roles пользователей, покинувших сервер.
    - Удаляет лидеров групп, покинувших сервер.
    - НЕ удаляет расписания повторяющихся событий (memory.schedules)!
    """
    now = datetime.now()

    # --- Чистка active_events: события старше месяца или без сообщения ---
    for guild_id, events in list(active_events.items()):
        for event in events[:]:
            try:
                # Получаем дату события
                event_dt = None
                for fmt in ("%d.%m.%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M"):
                    try:
                        event_dt = datetime.strptime(event["event_info"]["datetime"], fmt)
                        break
                    except Exception:
                        continue
                # Событие прошло более месяца назад — удаляем
                if event_dt and (now - event_dt).days > EVENT_EXPIRY_DAYS:
                    events.remove(event)
                    continue
                # Сообщение уже не существует — удаляем
                channel = bot.get_channel(event["channel_id"])
                if channel is None:
                    try:
                        channel = await bot.fetch_channel(event["channel_id"])
                    except Exception:
                        events.remove(event)
                        continue
                try:
                    await channel.fetch_message(event["message_id"])
                except Exception:
                    events.remove(event)
            except Exception:
                events.remove(event)

    # --- Собираем id всех участников каждого сервера ---
    guild_id_to_member_ids = {guild.id: set(member.id for member in guild.members) for guild in bot.guilds}

    # --- Чистка пресетов, user_roles, group_leaders по каждой гильдии ---
    for guild_id, member_ids in guild_id_to_member_ids.items():
        # Пресеты: удаляем из групп участников, которых нет на сервере
        if guild_id in memory.presets:
            for group in memory.presets[guild_id]:
                group[:] = [uid for uid in group if uid in member_ids]

        # user_roles: удаляем роли ушедших
        if guild_id in memory.user_roles:
            to_remove_roles = [uid for uid in memory.user_roles[guild_id] if uid not in member_ids]
            for uid in to_remove_roles:
                memory.user_roles[guild_id].pop(uid, None)

        # group_leaders: удаляем лидеров, которых нет на сервере
        if guild_id in memory.group_leaders:
            to_remove_leaders = [group_idx for group_idx, leader_uid in memory.group_leaders[guild_id].items() if leader_uid not in member_ids]
            for group_idx in to_remove_leaders:
                memory.group_leaders[guild_id].pop(group_idx, None)