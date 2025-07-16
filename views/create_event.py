import discord
from storage.memory import active_events, EventState, memory
from logic.render import render_groups_embed
from views.participant import ParticipantView
from datetime import datetime
from views.channel_select import ChannelSelectView

# Добавлено для работы с часовым поясом Москвы
try:
    from zoneinfo import ZoneInfo
    moscow_tz = ZoneInfo("Europe/Moscow")
except ImportError:
    import pytz
    moscow_tz = pytz.timezone("Europe/Moscow")

class CreateEventModal(discord.ui.Modal, title="Создание события"):
    name = discord.ui.TextInput(
        label="Название события",
        placeholder="Например: Riftstone",
        required=True
    )
    date = discord.ui.TextInput(
        label="Дата (ДД.ММ.ГГГГ)",
        placeholder="Пример: 06.07.2025",
        required=True
    )
    time = discord.ui.TextInput(
        label="Время (чч:мм)",
        placeholder="Пример: 20:00",
        required=True
    )
    comment = discord.ui.TextInput(
        label="Комментарий (необязательно)",
        placeholder="Например: не забудьте зелья",
        style=discord.TextStyle.paragraph,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        date_str = self.date.value.strip()
        time_str = self.time.value.strip()
        dt_str = f"{date_str} {time_str}"
        try:
            dt_naive = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
            # Привязываем к московскому времени
            dt = dt_naive.replace(tzinfo=moscow_tz)
            dt_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            await interaction.response.send_message(
                f"❌ Некорректная дата или время! Используй формат ДД.ММ.ГГГГ и чч:мм.",
                ephemeral=True
            )
            return

        event_info = {
            "name": str(self.name),
            "datetime": dt_str,
            "comment": str(self.comment or "—"),
            "created_by": interaction.user.id,
            "created_at": datetime.now(moscow_tz).isoformat()  # фиксируем время создания по Москве
        }

        async def after_channel_selected(new_interaction, channel_id):
            event_info["selected_channel_id"] = channel_id
            channel = new_interaction.guild.get_channel(channel_id)
            event_state = EventState()
            embed = render_groups_embed(event_info, event_state)
            view = ParticipantView(event_state, guild_id)
            if guild_id not in active_events:
                active_events[guild_id] = []
            sent_message = await channel.send(embed=embed, view=view)
            active_events[guild_id].append({
                "message_id": sent_message.id,
                "channel_id": sent_message.channel.id,
                "event_info": event_info,
                "event_state": event_state
            })
            # Удаляем подтверждающее сообщение через 10 сек
            await new_interaction.response.send_message("📨 Событие создано!", ephemeral=False, delete_after=10)

        view = ChannelSelectView(interaction.client, after_channel_selected)
        await view.setup(interaction.guild)
        # Сообщение выбора канала удалится через 15 сек
        await interaction.response.send_message(
            "Выберите канал для публикации события:",
            view=view,
            ephemeral=False,
            delete_after=15
        )