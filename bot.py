import os
from dotenv import load_dotenv

load_dotenv()  # Локально загрузит .env, на Railway возьмёт переменные окружения

import discord
from discord.ext import commands, tasks
from config import ALLOWED_ROLES
from views.participant import ParticipantView
from views.admin_panel import AdminPanelView
from logic.render import render_groups_embed
from storage.memory import active_events, EventState, memory
from storage.persist import (
    load_presets, load_user_roles, save_user_roles,
    load_schedules, save_schedules
)
from sync_presets import sync_presets_to_event_state
from datetime import datetime, timedelta
from discord.errors import NotFound

from cleanup import cleanup_events_and_members
from views.channel_select import ChannelSelectView

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Инициализация хранилища по всем гильдиям ---
@bot.event
async def on_ready():
    for guild in bot.guilds:
        load_presets(guild.id)
        load_user_roles(guild.id)
        load_schedules(guild.id)
    sync_presets_to_event_state()
    print(f"✅ Бот запущен как {bot.user}")
    update_event_embeds.start()
    recurring_event_scheduler.start()
    weekly_cleanup.start()
    event_autocleanup.start()

@bot.command(name="админ_панель")
async def admin_panel(ctx):
    if not any(role.name in ALLOWED_ROLES for role in ctx.author.roles):
        return await ctx.send("⛔ У тебя нет прав доступа.", delete_after=10)
    await ctx.send("🔧 Панель администратора:", view=AdminPanelView(ctx.guild.id), delete_after=30)

@bot.command(name="роль")
async def set_role(ctx, *, role: str):
    if ctx.message.mentions and ctx.author not in ctx.message.mentions:
        return await ctx.send("❌ Вы не можете менять роль другому пользователю.", delete_after=10)

    role = role.lower()
    user_id = ctx.author.id
    guild_id = ctx.guild.id
    if guild_id not in memory.user_roles:
        memory.user_roles[guild_id] = {}
    if role in ["танк", "tank"]:
        memory.user_roles[guild_id][user_id] = "танк"
        save_user_roles(guild_id)
        await ctx.send("🛡 Роль установлена: Танк", delete_after=10)
    elif role in ["хил", "healer", "хилер"]:
        memory.user_roles[guild_id][user_id] = "хил"
        save_user_roles(guild_id)
        await ctx.send("💉 Роль установлена: Хил", delete_after=10)
    elif role in ["дд", "dd"]:
        memory.user_roles[guild_id][user_id] = "дд"
        save_user_roles(guild_id)
        await ctx.send("⚔ Роль установлена: ДД", delete_after=10)
    else:
        await ctx.send("❌ Неизвестная роль. Доступные: танк, хил, дд", delete_after=10)
        return
    for event in active_events.get(guild_id, []):
        state = event["event_state"]
        if user_id in state.user_roles:
            state.set_user_role(user_id, memory.user_roles[guild_id][user_id])

@tasks.loop(minutes=1)
async def update_event_embeds():
    for guild_id, events in list(active_events.items()):
        for event in events[:]:
            try:
                channel = bot.get_channel(event["channel_id"])
                if not channel:
                    continue
                msg = await channel.fetch_message(event["message_id"])
                embed = render_groups_embed(event["event_info"], event["event_state"])
                await msg.edit(embed=embed)
            except NotFound:
                events.remove(event)
            except Exception as e:
                print(f"[ERROR] Не удалось обновить embed: {e}")

@tasks.loop(minutes=1)
async def recurring_event_scheduler():
    now = datetime.now()
    has_new_event = False
    for guild_id, schedules in memory.schedules.items():
        for sched in schedules:
            next_run = sched.get("next_run")
            if not next_run:
                continue
            if isinstance(next_run, str):
                parsed = False
                for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
                    try:
                        next_run_dt = datetime.strptime(next_run, fmt)
                        parsed = True
                        break
                    except Exception:
                        continue
                if not parsed:
                    continue
            else:
                next_run_dt = next_run
            if now >= next_run_dt:
                has_new_event = True
                event_info = {
                    "name": sched.get("name", "Событие"),
                    "datetime": next_run_dt.strftime("%d.%m.%Y %H:%M"),
                    "comment": sched.get("comment", "—"),
                    "created_by": sched.get("created_by"),
                    "is_recurring": True,
                    "recurring_start_date": sched.get("recurring_start_date") or sched.get("start_date"),
                    "recurring_interval_days": sched.get("interval_days"),
                    "schedule_id": sched.get("schedule_id", None),
                    "created_at": datetime.now().isoformat(),
                    "selected_channel_id": sched.get("selected_channel_id")
                }
                event_state = EventState()
                embed = render_groups_embed(event_info, event_state)
                target_channel = None
                ch_id = sched.get("selected_channel_id")
                if ch_id:
                    target_channel = bot.get_channel(ch_id)
                if not target_channel and active_events.get(guild_id):
                    ch_id = active_events[guild_id][0]["channel_id"]
                    target_channel = bot.get_channel(ch_id)
                elif not target_channel and hasattr(bot, "guilds") and bot.guilds:
                    for guild in bot.guilds:
                        if guild.id == guild_id:
                            for ch in guild.text_channels:
                                if ch.permissions_for(guild.me).send_messages:
                                    target_channel = ch
                                    break
                            break
                if target_channel:
                    view = ParticipantView(event_state, guild_id)
                    sent_message = await target_channel.send(embed=embed, view=view)
                    if guild_id not in active_events:
                        active_events[guild_id] = []
                    active_events[guild_id].append({
                        "message_id": sent_message.id,
                        "channel_id": sent_message.channel.id,
                        "event_info": event_info,
                        "event_state": event_state
                    })
                    sched["message_id"] = sent_message.id
                    sched["channel_id"] = sent_message.channel.id
                interval_days = sched.get("interval_days", 1)
                try:
                    interval_days = int(interval_days)
                except Exception:
                    interval_days = 1
                next_run_dt = next_run_dt + timedelta(days=interval_days)
                sched["next_run"] = next_run_dt.strftime("%d.%m.%Y %H:%M")
    if has_new_event:
        for guild in bot.guilds:
            save_schedules(guild.id)

@tasks.loop(hours=168)
async def weekly_cleanup():
    await cleanup_events_and_members(bot)

@tasks.loop(hours=24)
async def event_autocleanup():
    now = datetime.now()
    for guild_id, events in list(active_events.items()):
        to_remove = []
        for event in events:
            event_created = event["event_info"].get("created_at")
            if event_created:
                try:
                    created_dt = datetime.fromisoformat(event_created)
                    if now - created_dt > timedelta(days=30):
                        to_remove.append(event)
                except Exception:
                    continue
        for event in to_remove:
            try:
                channel = bot.get_channel(event["channel_id"])
                if not channel:
                    continue
                msg = await channel.fetch_message(event["message_id"])
                await msg.delete()
            except Exception:
                pass
            events.remove(event)

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError("Discord token not found! Set DISCORD_TOKEN in .env or environment.")

bot.run(TOKEN)