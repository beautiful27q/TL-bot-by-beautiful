import discord
from storage.memory import memory, active_events, EventState
from logic.render import render_groups_embed
from views.participant import ParticipantView
from datetime import datetime, timedelta
from sync_presets import sync_presets_to_event_state
import uuid
from storage.persist import save_schedules
from views.channel_select import ChannelSelectView

# Работа с часовым поясом Москвы через pytz
import pytz
moscow_tz = pytz.timezone("Europe/Moscow")

class RecurringEventModal(discord.ui.Modal, title="Создание повторяющегося события"):
    name = discord.ui.TextInput(label="Название события", placeholder="Например: Riftstone", required=True)
    start_date = discord.ui.TextInput(label="Дата старта (ДД.ММ.ГГГГ)", placeholder="08.07.2025", required=True)
    time = discord.ui.TextInput(label="Время (чч:мм)", placeholder="Пример: 20:00", required=True)
    interval = discord.ui.TextInput(label="Каждые N дней", placeholder="Например: 3", required=True)
    comment = discord.ui.TextInput(label="Комментарий", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        try:
            start_date_str = self.start_date.value.strip()
            try:
                start_date_naive = datetime.strptime(start_date_str, "%d.%m.%Y")
            except Exception:
                await interaction.response.send_message(
                    f"❌ Некорректная дата! Используй формат ДД.ММ.ГГГГ, например: 08.07.2025",
                    ephemeral=True
                )
                return

            try:
                hour, minute = map(int, self.time.value.strip().split(":"))
            except Exception:
                await interaction.response.send_message(
                    f"❌ Некорректное время! Используй формат чч:мм, например: 20:00",
                    ephemeral=True
                )
                return

            interval_days = int(self.interval.value.strip())

            # Дата и время старта первого события
            start_dt_naive = start_date_naive.replace(hour=hour, minute=minute, second=0, microsecond=0)
            start_dt = moscow_tz.localize(start_dt_naive)
            now = datetime.now(moscow_tz)

            # Сколько прошло дней от старта до сейчас
            days_passed = (now - start_dt).days
            intervals_passed = max(0, (days_passed // interval_days) + 1)
            event_start = start_dt + timedelta(days=intervals_passed * interval_days)

            # Время публикации события за 3 часа до начала
            next_run = event_start - timedelta(hours=3)
            # Если next_run в прошлом — поднимаем к следующему циклу
            while next_run <= now:
                event_start += timedelta(days=interval_days)
                next_run = event_start - timedelta(hours=3)

            schedule_id = str(uuid.uuid4())

            async def after_channel_selected(new_interaction, channel_id):
                sched_obj = {
                    "schedule_id": schedule_id,
                    "name": self.name.value,
                    "interval_days": interval_days,
                    "comment": self.comment.value,
                    "next_run": next_run.isoformat(),  # Когда публиковать следующее событие
                    "event_start": event_start.isoformat(),  # Когда начнётся само событие
                    "created_by": interaction.user.id,
                    "recurring_start_date": start_date_str,
                    "selected_channel_id": channel_id,
                    "created_at": datetime.now(moscow_tz).isoformat()
                }
                if guild_id not in memory.schedules:
                    memory.schedules[guild_id] = []
                memory.schedules[guild_id].append(sched_obj)
                save_schedules(guild_id)

                await new_interaction.response.send_message(
                    f"✅ Запланировано событие **{self.name.value}** каждые {interval_days} дн. с {start_date_str} в {hour:02d}:{minute:02d}. "
                    f"Публикация за 3 часа до старта.",
                    ephemeral=False,
                    delete_after=10
                )

                sync_presets_to_event_state(guild_id)
                channel = new_interaction.guild.get_channel(channel_id)
                if channel is not None:
                    event_info = {
                        "name": str(self.name.value),
                        "datetime": event_start.isoformat(),  # Время самого события
                        "comment": str(self.comment.value or "—"),
                        "created_by": interaction.user.id,
                        "is_recurring": True,
                        "recurring_start_date": start_date_str,
                        "recurring_interval_days": interval_days,
                        "schedule_id": schedule_id,
                        "created_at": datetime.now(moscow_tz).isoformat(),
                        "selected_channel_id": channel_id
                    }
                    event_state = EventState()
                    embed = render_groups_embed(event_info, event_state)
                    view = ParticipantView(event_state, guild_id)
                    if guild_id not in active_events:
                        active_events[guild_id] = []
                    sent_message = await channel.send(
                        content="🔁 Повторяющееся событие",
                        embed=embed,
                        view=view
                    )
                    active_events[guild_id].append({
                        "message_id": sent_message.id,
                        "channel_id": sent_message.channel.id,
                        "event_info": event_info,
                        "event_state": event_state
                    })
                    sched_obj["message_id"] = sent_message.id
                    sched_obj["channel_id"] = sent_message.channel.id
                    save_schedules(guild_id)

            view = ChannelSelectView(interaction.client, after_channel_selected)
            await view.setup(interaction.guild)
            await interaction.response.send_message(
                "Выберите канал для публикации события:",
                view=view,
                ephemeral=False,
                delete_after=15
            )

        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка в данных: {str(e)}", ephemeral=True)