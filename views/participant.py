import discord
from discord import ui, ButtonStyle, Interaction
from logic.render import render_groups_embed
from storage.memory import active_events, memory
from storage.persist import save_user_roles
import traceback

def find_event_by_state(event_state, guild_id):
    for event in active_events.get(guild_id, []):
        if event["event_state"] is event_state:
            return event
    return None

class RoleSelectView(discord.ui.View):
    def __init__(self, event_state, user_id, guild_id):
        super().__init__(timeout=60)
        self.event_state = event_state
        self.user_id = user_id
        self.guild_id = guild_id

    @discord.ui.button(label="🛡️ Танк", style=discord.ButtonStyle.primary)
    async def tank(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_role(interaction, "танк")

    @discord.ui.button(label="💉 Хил", style=discord.ButtonStyle.success)
    async def healer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_role(interaction, "хил")

    @discord.ui.button(label="⚔️ ДД", style=discord.ButtonStyle.danger)
    async def dd(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_role(interaction, "дд")

    async def set_role(self, interaction, role):
        # Сохраняем роль пользователя в глобальный user_roles по гильдии
        if self.guild_id not in memory.user_roles:
            memory.user_roles[self.guild_id] = {}
        memory.user_roles[self.guild_id][self.user_id] = role
        save_user_roles(self.guild_id)
        # В текущем событии сохраняем роль только если пользователь реально участвует
        self.event_state.set_user_role(self.user_id, role)
        self.event_state.join(self.user_id, self.guild_id)  # Передаём guild_id!
        await interaction.response.send_message(
            f"Роль выбрана: {role.capitalize()}. Ты участвуешь в событии!",
            ephemeral=True
        )
        await update_event_message(interaction, self.event_state, self.guild_id)
        self.stop()

async def update_event_message(interaction, event_state, guild_id):
    print(f"update_event_message called for guild {guild_id}")
    event = find_event_by_state(event_state, guild_id)
    if not event:
        print(f"[WARN] Event not found for guild_id {guild_id}")
        return
    channel = interaction.guild.get_channel(event["channel_id"])
    if not channel:
        channel = await interaction.client.fetch_channel(event["channel_id"])
    try:
        message = await channel.fetch_message(event["message_id"])
    except Exception as e:
        print(f'Ошибка получения сообщения: {e}')
        traceback.print_exc()
        return
    event_info = event["event_info"]
    updated_embed = render_groups_embed(event_info, event_state)
    try:
        await message.edit(embed=updated_embed, view=ParticipantView(event_state, guild_id))
        print("update_event_message finished")
    except Exception as e:
        print(f'Ошибка обновления embed: {e}')
        traceback.print_exc()

class ParticipantView(ui.View):
    def __init__(self, event_state, guild_id):
        super().__init__(timeout=None)
        self.event_state = event_state
        self.guild_id = guild_id

    @ui.button(label="✅ Участвовать", style=ButtonStyle.success, custom_id="join_event")
    async def join(self, interaction: Interaction, button: ui.Button):
        user_id = interaction.user.id
        user_role = self.event_state.user_roles.get(user_id)
        if not user_role:
            # Не участвует в этом событии — предлагаем выбрать роль, не подтягиваем из memory.user_roles!
            await interaction.response.send_message(
                "Выберите роль для участия:",
                view=RoleSelectView(self.event_state, user_id, self.guild_id),
                ephemeral=True
            )
            return
        # Если уже участвовал и выбрал роль — просто перезаписываем
        self.event_state.set_user_role(user_id, user_role)
        # memory.user_roles обновляем для !роль
        if self.guild_id not in memory.user_roles:
            memory.user_roles[self.guild_id] = {}
        memory.user_roles[self.guild_id][user_id] = user_role
        save_user_roles(self.guild_id)
        self.event_state.join(user_id, self.guild_id)  # Передаём guild_id!
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} участвует в событии!", ephemeral=True
        )
        await update_event_message(interaction, self.event_state, self.guild_id)

    @ui.button(label="❌ Отменить", style=ButtonStyle.danger, custom_id="leave_event")
    async def leave(self, interaction: Interaction, button: ui.Button):
        user_id = interaction.user.id
        self.event_state.leave(user_id, self.guild_id)  # Передаём guild_id!
        await interaction.response.send_message(
            f"🚪 {interaction.user.mention} покинул событие.", ephemeral=True
        )
        await update_event_message(interaction, self.event_state, self.guild_id)

    @ui.button(label="🚫 Не смогу", style=discord.ButtonStyle.secondary, custom_id="decline_event")
    async def decline(self, interaction: Interaction, button: ui.Button):
        user_id = interaction.user.id
        self.event_state.decline(user_id, self.guild_id)  # Передаём guild_id!
        await interaction.response.send_message(
            f"😔 {interaction.user.mention} отметил 'не смогу'.", ephemeral=True
        )
        await update_event_message(interaction, self.event_state, self.guild_id)