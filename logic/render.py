import discord
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from storage.memory import memory  # <--- Добавлено для доступа к глобальным ролям

import pytz
moscow_tz = pytz.timezone("Europe/Moscow")  # FIX: импорт и объявление таймзоны

def get_username(user_id: int) -> str:
    return f"<@{user_id}>"

ROLE_EMOJIS = {
    "лидер": "👑",
    "танк": "🛡️",
    "хил": "💉",
    "дд": "⚔️",
    "дд1": "⚔️",
    "дд2": "⚔️",
    "дд3": "⚔️",
    "дд4": "⚔️",
    "нет": "❌"
}

def humanize_timedelta(event_dt: datetime) -> str:
    # FIX: если event_dt содержит tzinfo, берём now тоже с таймзоной
    if event_dt and event_dt.tzinfo:
        now = datetime.now(event_dt.tzinfo)
    else:
        now = datetime.now(moscow_tz)
    delta = event_dt - now
    total_seconds = int(delta.total_seconds())

    if total_seconds >= 0:
        minutes = (total_seconds // 60) % 60
        hours = (total_seconds // 3600) % 24
        days = total_seconds // 86400
        if days > 0:
            return f"через {days} дн. {hours} ч."
        elif hours > 0:
            return f"через {hours} ч. {minutes} мин."
        else:
            return f"через {minutes} мин."
    else:
        total_seconds = abs(total_seconds)
        minutes = (total_seconds // 60) % 60
        hours = (total_seconds // 3600) % 24
        days = total_seconds // 86400
        if days > 0:
            ago_str = f"{days} дн. {hours} ч. назад"
        elif hours > 0:
            ago_str = f"{hours} ч. {minutes} мин. назад"
        else:
            ago_str = f"{minutes} мин. назад"
        return f"**🔴 Завершено {ago_str}**"

def render_declined(declined: List[int], user_roles: Dict[int, str], event_guild_id: Optional[int] = None) -> Optional[str]:
    if not declined:
        return None
    role_map = {
        "танк": "Танк",
        "хил": "Хил",
        "дд": "ДД",
        "дд1": "ДД",
        "дд2": "ДД",
        "дд3": "ДД",
        "дд4": "ДД"
    }
    lines = []
    for uid in declined:
        # Получаем роль сначала из локального event_state, потом из глобального хранилища
        role_key = user_roles.get(uid)
        if not role_key and event_guild_id is not None:
            # Берём глобальную роль, если есть
            role_key = memory.user_roles.get(event_guild_id, {}).get(uid, 'нет')
        if not role_key:
            role_key = 'нет'
        role_str = role_map.get(role_key, "Нет") if role_key != "нет" else "Нет"
        emoji = ROLE_EMOJIS.get(role_key, "❌")
        lines.append(f"{emoji} {get_username(uid)} ({role_str})")
    return "❌ **Не смогут:**\n" + "\n".join(lines)

def render_group(group: Dict[str, Optional[int]], idx: int) -> str:
    lines = [f"**Группа {idx+1}**"]
    leader_uid = group.get("лидер")
    if leader_uid is not None:
        lines.append(f"{ROLE_EMOJIS['лидер']} Лидер: {get_username(leader_uid)}")
    else:
        lines.append(f"{ROLE_EMOJIS['нет']} Лидер: Нет")
    for role in ["танк", "хил", "дд1", "дд2", "дд3", "дд4"]:
        uid = group.get(role)
        if uid is not None:
            role_disp = {
                "танк": "Танк",
                "хил": "Хил",
                "дд1": "ДД1",
                "дд2": "ДД2",
                "дд3": "ДД3",
                "дд4": "ДД4",
            }.get(role, role.capitalize())
            lines.append(f"{ROLE_EMOJIS.get(role if role in ROLE_EMOJIS else 'дд', '❌')} {role_disp}: {get_username(uid)}")
        else:
            role_disp = {
                "танк": "Танк",
                "хил": "Хил",
                "дд1": "ДД1",
                "дд2": "ДД2",
                "дд3": "ДД3",
                "дд4": "ДД4",
            }.get(role, role.capitalize())
            lines.append(f"{ROLE_EMOJIS.get('нет', '❌')} {role_disp}: Нет")
    return "\n".join(lines)

def render_groups(groups: List[Dict[str, Optional[int]]]) -> List[str]:
    fields = []
    for i in range(0, len(groups), 3):
        chunk = groups[i:i+3]
        for j, group in enumerate(chunk):
            fields.append(render_group(group, i+j))
        for _ in range(3 - len(chunk)):
            fields.append("\u200b")
    return fields

def build_event_embed(
    event_info: dict,
    event_state,
    color: int = 0x00aaff
) -> discord.Embed:
    is_recurring = event_info.get("is_recurring", False)
    title_icon = "🔁🛡️" if is_recurring else "🛡️"
    title = f"{title_icon} {event_info.get('name', 'Событие')}"
    description_lines = []
    raw_dt = event_info.get('datetime', '—')

    # FIX: корректный парсинг ISO-строки с таймзоной
    dt = None
    try:
        dt = datetime.fromisoformat(raw_dt)
        dt_str = dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        # Если вдруг не ISO, пробуем старые форматы
        for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
            try:
                dt = datetime.strptime(raw_dt, fmt)
                dt_str = dt.strftime("%d.%m.%Y %H:%M")
                break
            except Exception:
                dt_str = raw_dt

    description_lines.append(f"**Начало:** {dt_str}")

    comment = event_info.get('comment', None)
    if comment:
        description_lines.append(f"💬 {comment}")

    description = "\n".join(description_lines)

    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )

    # Получаем guild_id для поиска глобальных ролей
    guild_id = event_info.get("guild_id") or event_info.get("guild", {}).get("id")
    declined_block = render_declined(event_state.get_declined_list(), event_state.user_roles, guild_id)
    if declined_block:
        embed.add_field(name="\u200b", value=declined_block, inline=False)

    group_datas = event_state.get_group_data()
    group_fields = render_groups(group_datas)
    for i in range(0, len(group_fields), 3):
        chunk = group_fields[i:i+3]
        for j, group_str in enumerate(chunk):
            embed.add_field(
                name="\u200b",
                value=group_str,
                inline=True
            )

    # FIX: считаем время до события по ISO-строке
    event_dt = dt
    time_left_str = humanize_timedelta(event_dt) if event_dt else "—"

    embed.add_field(
        name="⏳ Время",
        value=time_left_str,
        inline=True
    )

    if event_dt and event_dt < (datetime.now(event_dt.tzinfo) if event_dt.tzinfo else datetime.now(moscow_tz)):
        status_str = "🔴 Событие завершено"
    else:
        status_str = "🟢 Регистрация открыта"

    embed.add_field(
        name="🟢 Статус",
        value=status_str,
        inline=True
    )

    if is_recurring:
        embed.set_footer(text="🔁 Повторяющееся событие • \n🐧 Created by beautiful")
    else:
        embed.set_footer(text="🐧 Created by beautiful")

    return embed

def build_event_buttons(registration_open: bool) -> discord.ui.View:
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="✅ Участвовать",
            custom_id="event_join",
            disabled=not registration_open
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="❌ Отменить",
            custom_id="event_leave",
            disabled=not registration_open
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🚫 Не смогу",
            custom_id="event_decline",
            disabled=not registration_open
        )
    )
    return view

render_groups_embed = build_event_embed