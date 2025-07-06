import discord
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

def get_username(user_id: int) -> str:
    return f"<@{user_id}>"

ROLE_EMOJIS = {
    "лидер": "👑",
    "танк": "🛡️",
    "хил": "💉",
    "дд1": "⚔️",
    "дд2": "⚔️",
    "дд3": "⚔️",
    "дд4": "⚔️",
    "нет": "❌"
}

def humanize_timedelta(event_dt: datetime) -> str:
    now = datetime.now()
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

def render_declined(declined: List[int], user_roles: Dict[int, str]) -> Optional[str]:
    if not declined:
        return None
    lines = [
        f"{ROLE_EMOJIS.get(user_roles.get(uid, 'нет'), '❌')} {get_username(uid)} ({user_roles.get(uid, 'нет')})"
        for uid in declined
    ]
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
            lines.append(f"{ROLE_EMOJIS.get(role, '❌')} {role.capitalize()}: {get_username(uid)}")
        else:
            lines.append(f"{ROLE_EMOJIS.get('нет', '❌')} {role.capitalize()}: Нет")
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
    # --- Title: с иконкой если повторяющееся ---
    title_icon = "🔁🛡️" if is_recurring else "🛡️"
    title = f"{title_icon} {event_info.get('name', 'Событие')}"

    # --- Description: только нужное ---
    description_lines = []

    # Получаем дату события и приводим к формату "ДД.ММ.ГГГГ чч:мм"
    raw_dt = event_info.get('datetime', '—')
    try:
        dt = None
        for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
            try:
                dt = datetime.strptime(raw_dt, fmt)
                break
            except Exception:
                continue
        if dt:
            dt_str = dt.strftime("%d.%m.%Y %H:%M")
        else:
            dt_str = raw_dt
    except Exception:
        dt_str = raw_dt

    description_lines.append(f"**Начало:** {dt_str}")

    # Комментарий к событию (если есть)
    comment = event_info.get('comment', None)
    if comment:
        description_lines.append(f"💬 {comment}")

    description = "\n".join(description_lines)

    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )

    # --- declined пользователей (вывод "не смогут")
    # event_state.user_roles теперь должен быть везде локальным для события!
    declined_block = render_declined(event_state.get_declined_list(), event_state.user_roles)
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

    # Время до события / после события
    event_dt = None
    try:
        for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
            try:
                event_dt = datetime.strptime(event_info.get('datetime'), fmt)
                break
            except Exception:
                continue
    except Exception:
        pass
    time_left_str = humanize_timedelta(event_dt) if event_dt else "—"

    embed.add_field(
        name="⏳ Время",
        value=time_left_str,
        inline=True
    )

    if event_dt and event_dt < datetime.now():
        status_str = "🔴 Событие завершено"
    else:
        status_str = "🟢 Регистрация открыта"

    embed.add_field(
        name="🟢 Статус",
        value=status_str,
        inline=True
    )

    # Footer: разные эмодзи для обычного и повторяющегося события
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

# Алиас для совместимости со старым импортом
render_groups_embed = build_event_embed