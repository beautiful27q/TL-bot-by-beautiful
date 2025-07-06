import discord
from storage.memory import memory, active_events, EventState  # Исправлен импорт
from logic.render import render_groups_embed
from views.participant import ParticipantView
from datetime import datetime, timedelta
from sync_presets import sync_presets_to_event_state
import uuid
from storage.persist import save_schedules
from views.channel_select import ChannelSelectView

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
                start_date = datetime.strptime(start_date_str, "%d.%m.%Y")
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
            next_run = start_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            now = datetime.now()
            while next_run <= now:
                next_run += timedelta(days=interval_days)

            schedule_id = str(uuid.uuid4())

            async def after_channel_selected(new_interaction, channel_id):
                sched_obj = {
                    "schedule_id": schedule_id,
                    "name": self.name.value,
                    "interval_days": interval_days,
                    "comment": self.comment.value,
                    "next_run": next_run.strftime("%d.%m.%Y %H:%M"),
                    "created_by": interaction.user.id,
                    "recurring_start_date": start_date_str,
                    "selected_channel_id": channel_id,
                    "created_at": datetime.now().isoformat()
                }
                if guild_id not in memory.schedules:
                    memory.schedules[guild_id] = []
                memory.schedules[guild_id].append(sched_obj)
                save_schedules(guild_id)

                await new_interaction.response.send_message(
                    f"✅ Запланировано событие **{self.name.value}** каждые {interval_days} дн. с {start_date_str} в {hour:02d}:{minute:02d}",
                    ephemeral=True
                )

                sync_presets_to_event_state(guild_id)
                channel = new_interaction.guild.get_channel(channel_id)
                if channel is not None:
                    dt_str = next_run.strftime("%d.%m.%Y %H:%M")
                    event_info = {
                        "name": str(self.name.value),
                        "datetime": dt_str,
                        "comment": str(self.comment.value or "—"),
                        "created_by": interaction.user.id,
                        "is_recurring": True,
                        "recurring_start_date": start_date_str,
                        "recurring_interval_days": interval_days,
                        "schedule_id": schedule_id,
                        "created_at": datetime.now().isoformat(),
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
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка в данных: {str(e)}", ephemeral=True)