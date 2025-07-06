import discord
from discord import ButtonStyle
from storage.memory import memory  # Исправлен импорт
from storage.persist import save_presets, save_schedules
from views.create_event import CreateEventModal
from views.recurring_event import RecurringEventModal
from sync_presets import sync_presets_to_event_state
import datetime

# --- Preset Selection ---
class PresetSelectView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.add_item(PresetMemberSelect(guild_id))

class PresetMemberSelect(discord.ui.Select):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        used_ids = set(uid for group in memory.presets.get(guild_id, []) for uid in group)
        member_list = memory.last_member_list.get(guild_id, [])
        options = [
            discord.SelectOption(label=member.name, value=str(member.id))
            for member in member_list
            if not member.bot and member.id not in used_ids
        ]
        super().__init__(
            placeholder="Выберите до 6 участников для пресет-группы",
            min_values=1,
            max_values=6,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        selected = [int(uid) for uid in self.values]
        already_in_group = []
        for uid in selected:
            for group in memory.presets.get(guild_id, []):
                if uid in group:
                    already_in_group.append(uid)
                    break
        if already_in_group:
            members = [interaction.guild.get_member(uid) for uid in already_in_group]
            names = ', '.join(m.mention if m else str(uid) for m, uid in zip(members, already_in_group))
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"❌ Эти участники уже состоят в других пресет-группах: {names}\n"
                    f"Удалите их из других групп перед добавлением.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ Эти участники уже состоят в других пресет-группах: {names}\n"
                    f"Удалите их из других групп перед добавлением.",
                    ephemeral=True
                )
            return
        group_number = len(memory.presets.get(guild_id, [])) + 1
        new_group = selected
        memory.presets.setdefault(guild_id, []).append(new_group)
        save_presets(guild_id)
        sync_presets_to_event_state(guild_id)
        if interaction.response.is_done():
            await interaction.followup.send(
                f"✅ Добавлена пресет-группа {group_number} с {len(new_group)} участниками.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"✅ Добавлена пресет-группа {group_number} с {len(new_group)} участниками.",
                ephemeral=True
            )

# --- Leader Selection ---
class LeaderSelectionView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        for index, group in enumerate(memory.presets.get(guild_id, [])[:25]):
            self.add_item(LeaderSelect(guild_id, index, group))

class LeaderSelect(discord.ui.Select):
    def __init__(self, guild_id, group_index, group_members):
        self.guild_id = guild_id
        member_list = memory.last_member_list.get(guild_id, [])
        options = [
            discord.SelectOption(label=f"@{member.display_name}", value=str(member.id))
            for member in member_list if member.id in group_members
        ]
        if not options:
            options = [discord.SelectOption(label="Нет кандидатов", value="none", default=True)]
        super().__init__(
            placeholder=f"Выбери лидера для Группы {group_index + 1}",
            min_values=1,
            max_values=1,
            options=options
        )
        self.group_index = group_index

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if self.values[0] == "none":
            if interaction.response.is_done():
                await interaction.followup.send("Нет кандидатов для лидера.", ephemeral=True)
            else:
                await interaction.response.send_message("Нет кандидатов для лидера.", ephemeral=True)
            return
        user_id = int(self.values[0])
        if user_id not in memory.presets[guild_id][self.group_index]:
            for idx, group in enumerate(memory.presets[guild_id]):
                if idx != self.group_index and user_id in group:
                    if interaction.response.is_done():
                        await interaction.followup.send(
                            f"❌ Этот пользователь уже состоит в другой пресет-группе. Сначала удалите его из той группы.",
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            f"❌ Этот пользователь уже состоит в другой пресет-группе. Сначала удалите его из той группы.",
                            ephemeral=True
                        )
                    return
            memory.presets[guild_id][self.group_index].append(user_id)
        memory.group_leaders.setdefault(guild_id, {})[self.group_index] = user_id
        print(f"[LOG] Назначен лидер для группы {self.group_index}: {user_id}")
        save_presets(guild_id)
        sync_presets_to_event_state(guild_id)
        member = interaction.guild.get_member(user_id)
        if interaction.response.is_done():
            await interaction.followup.send(
                f"👑 Лидер для Группы {self.group_index + 1} назначен: {member.mention}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"👑 Лидер для Группы {self.group_index + 1} назначен: {member.mention}",
                ephemeral=True
            )

# --- Schedule Management ---
class ScheduleManagementView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.add_item(ScheduleSelect(guild_id))

class ScheduleSelect(discord.ui.Select):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        options = []
        for index, sched in enumerate(memory.schedules.get(guild_id, [])):
            next_run = sched['next_run']
            if isinstance(next_run, str):
                try:
                    next_run_dt = datetime.datetime.strptime(next_run, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    next_run_dt = next_run
            else:
                next_run_dt = next_run
            description = (
                f"Следующее: {next_run_dt.strftime('%d.%m %H:%M')}" 
                if hasattr(next_run_dt, 'strftime')
                else f"Следующее: {next_run_dt}"
            )
            options.append(
                discord.SelectOption(
                    label=f"{sched['name']} — каждые {sched['interval_days']} дн.",
                    description=description,
                    value=str(index)
                )
            )
        if not options:
            options = [discord.SelectOption(label="Нет активных событий", value="none", default=True)]
        super().__init__(
            placeholder="Выберите событие для удаления",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if self.values[0] == "none":
            if interaction.response.is_done():
                await interaction.followup.send("Нет событий для удаления.", ephemeral=True)
            else:
                await interaction.response.send_message("Нет событий для удаления.", ephemeral=True)
            return
        index = int(self.values[0])
        sched = memory.schedules[guild_id].pop(index)
        save_schedules(guild_id)
        msg_id = sched.get("message_id")
        ch_id = sched.get("channel_id")
        # Удаляем из active_events по message_id/channel_id
        to_remove = None
        for event in getattr(memory, "active_events", {}).get(guild_id, []):
            if event.get("message_id") == msg_id and event.get("channel_id") == ch_id:
                to_remove = event
                break
        if to_remove:
            getattr(memory, "active_events", {}).get(guild_id, []).remove(to_remove)
        # Пробуем удалить сообщение в Discord
        if msg_id and ch_id:
            try:
                guild = interaction.guild
                channel = guild.get_channel(ch_id) if guild else None
                if not channel:
                    channel = await interaction.client.fetch_channel(ch_id)
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
            except Exception:
                pass
        if interaction.response.is_done():
            await interaction.followup.send("✅ Расписание и сообщение удалены.", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Расписание и сообщение удалены.", ephemeral=True)

# --- Edit Presets (Advanced) ---
class EditPresetsView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.add_item(PresetGroupSelect(guild_id))

class PresetGroupSelect(discord.ui.Select):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(
                label=f"Группа {idx + 1}",
                description=f"{len(group)} участник(ов)",
                value=str(idx)
            )
            for idx, group in enumerate(memory.presets.get(guild_id, []))
        ]
        if not options:
            options = [discord.SelectOption(label="Нет групп", value="none", default=True)]
        super().__init__(
            placeholder="Выберите группу для редактирования",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if self.values[0] == "none":
            if interaction.response.is_done():
                await interaction.followup.send("Нет доступных групп.", ephemeral=True)
            else:
                await interaction.response.send_message("Нет доступных групп.", ephemeral=True)
            return
        group_index = int(self.values[0])
        group = memory.presets[guild_id][group_index]
        members = [interaction.guild.get_member(uid) for uid in group if interaction.guild.get_member(uid)]
        mentions = [m.mention for m in members]
        group_text = "\n".join(mentions)
        if interaction.response.is_done():
            await interaction.followup.send(
                f"✏️ Редактирование группы {group_index + 1}:\n{group_text}",
                view=PresetMemberEditView(guild_id, group_index, group),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"✏️ Редактирование группы {group_index + 1}:\n{group_text}",
                view=PresetMemberEditView(guild_id, group_index, group),
                ephemeral=True
            )

class PresetMemberEditView(discord.ui.View):
    def __init__(self, guild_id, group_index, group):
        super().__init__(timeout=120)
        self.add_item(PresetMemberEditSelect(guild_id, group_index, group))
        self.add_item(DeletePresetGroupButton(guild_id, group_index))

class PresetMemberEditSelect(discord.ui.Select):
    def __init__(self, guild_id, group_index, group):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label=f"@{member.display_name}", value=str(member.id))
            for member in memory.last_member_list.get(guild_id, []) if member.id in group
        ]
        if not options:
            options = [discord.SelectOption(label="Нет участников", value="none", default=True)]
        super().__init__(
            placeholder="Выберите участника для изменения",
            min_values=1,
            max_values=1,
            options=options
        )
        self.group_index = group_index

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if self.values[0] == "none":
            if interaction.response.is_done():
                await interaction.followup.send("Нет участников для изменения.", ephemeral=True)
            else:
                await interaction.response.send_message("Нет участников для изменения.", ephemeral=True)
            return
        user_id = int(self.values[0])
        if interaction.response.is_done():
            await interaction.followup.send(
                f"Участник выбран: <@{user_id}>. Выберите действие:",
                view=PresetMemberActionView(guild_id, self.group_index, user_id),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Участник выбран: <@{user_id}>. Выберите действие:",
                view=PresetMemberActionView(guild_id, self.group_index, user_id),
                ephemeral=True
            )

class PresetMemberActionView(discord.ui.View):
    def __init__(self, guild_id, group_index, user_id):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.group_index = group_index
        self.user_id = user_id

    @discord.ui.button(label="❌ Удалить из группы", style=discord.ButtonStyle.danger)
    async def remove_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        group = memory.presets[guild_id][self.group_index]
        if self.user_id in group:
            group.remove(self.user_id)
            if memory.group_leaders.get(guild_id, {}).get(self.group_index) == self.user_id:
                memory.group_leaders[guild_id][self.group_index] = None
            save_presets(guild_id)
            sync_presets_to_event_state(guild_id)
            if interaction.response.is_done():
                await interaction.followup.send(f"Участник <@{self.user_id}> удалён из группы.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Участник <@{self.user_id}> удалён из группы.", ephemeral=True)
        else:
            if interaction.response.is_done():
                await interaction.followup.send("Участник не найден в группе.", ephemeral=True)
            else:
                await interaction.response.send_message("Участник не найден в группе.", ephemeral=True)

    @discord.ui.button(label="➡️ Переместить в другую группу", style=discord.ButtonStyle.primary)
    async def move_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        count = len(memory.presets.get(guild_id, []))
        options = []
        for i in range(count):
            if i != self.group_index:
                options.append(discord.SelectOption(label=f"Группа {i+1}", value=str(i)))
        if not options:
            if interaction.response.is_done():
                await interaction.followup.send("Нет других групп для перемещения.", ephemeral=True)
            else:
                await interaction.response.send_message("Нет других групп для перемещения.", ephemeral=True)
            return
        if interaction.response.is_done():
            await interaction.followup.send(
                "Выберите целевую группу:",
                view=PresetMemberMoveTargetView(guild_id, self.group_index, self.user_id, options),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Выберите целевую группу:",
                view=PresetMemberMoveTargetView(guild_id, self.group_index, self.user_id, options),
                ephemeral=True
            )

class PresetMemberMoveTargetSelect(discord.ui.Select):
    def __init__(self, guild_id, from_group_index, user_id, options):
        self.guild_id = guild_id
        super().__init__(
            placeholder="Целевая группа",
            min_values=1,
            max_values=1,
            options=options
        )
        self.from_group_index = from_group_index
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        to_group_index = int(self.values[0])
        from_group = memory.presets[guild_id][self.from_group_index]
        while len(memory.presets[guild_id]) <= to_group_index:
            memory.presets[guild_id].append([])
        to_group = memory.presets[guild_id][to_group_index]
        if self.user_id in from_group:
            from_group.remove(self.user_id)
        if memory.group_leaders.get(guild_id, {}).get(self.from_group_index) == self.user_id:
            memory.group_leaders[guild_id][self.from_group_index] = None
        for idx, group in enumerate(memory.presets[guild_id]):
            if idx != self.from_group_index and self.user_id in group:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        f"❌ Этот пользователь уже состоит в другой пресет-группе. Сначала удалите его из той группы.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ Этот пользователь уже состоит в другой пресет-группе. Сначала удалите его из той группы.",
                        ephemeral=True
                    )
                return
        if self.user_id not in to_group:
            to_group.append(self.user_id)
        save_presets(guild_id)
        sync_presets_to_event_state(guild_id)
        if interaction.response.is_done():
            await interaction.followup.send(
                f"Участник <@{self.user_id}> перемещён в группу {to_group_index+1}.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Участник <@{self.user_id}> перемещён в группу {to_group_index+1}.",
                ephemeral=True
            )

class PresetMemberMoveTargetView(discord.ui.View):
    def __init__(self, guild_id, from_group_index, user_id, options):
        super().__init__(timeout=60)
        self.add_item(PresetMemberMoveTargetSelect(guild_id, from_group_index, user_id, options))

class DeletePresetGroupButton(discord.ui.Button):
    def __init__(self, guild_id, group_index):
        super().__init__(label="🗑️ Удалить эту группу", style=discord.ButtonStyle.danger)
        self.guild_id = guild_id
        self.group_index = group_index

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if 0 <= self.group_index < len(memory.presets.get(guild_id, [])):
            memory.presets[guild_id].pop(self.group_index)
            if self.group_index in memory.group_leaders.get(guild_id, {}):
                del memory.group_leaders[guild_id][self.group_index]
            # Пересчитываем индексы лидеров
            memory.group_leaders[guild_id] = {i if i < self.group_index else i-1: lid for i, lid in memory.group_leaders[guild_id].items() if i != self.group_index}
            save_presets(guild_id)
            sync_presets_to_event_state(guild_id)
            if interaction.response.is_done():
                await interaction.followup.send("Группа удалена.", ephemeral=True)
            else:
                await interaction.response.send_message("Группа удалена.", ephemeral=True)
        else:
            if interaction.response.is_done():
                await interaction.followup.send("Группа не найдена.", ephemeral=True)
            else:
                await interaction.response.send_message("Группа не найдена.", ephemeral=True)

class AdminPanelView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="🗓 Создать событие", style=ButtonStyle.primary, custom_id="create_event_modal")
    async def create_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CreateEventModal())

    @discord.ui.button(label="🔁 Повторяющееся событие", style=ButtonStyle.secondary, custom_id="create_schedule")
    async def create_schedule(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RecurringEventModal())

    @discord.ui.button(label="⚙️ Изменить повторяющееся событие", style=ButtonStyle.danger, custom_id="edit_schedule")
    async def edit_schedule(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        if not memory.schedules.get(guild_id, []):
            if interaction.response.is_done():
                await interaction.followup.send("Нет активных расписаний.", ephemeral=True)
            else:
                await interaction.response.send_message("Нет активных расписаний.", ephemeral=True)
            return
        if interaction.response.is_done():
            await interaction.followup.send(
                "Выберите расписание для удаления:",
                view=ScheduleManagementView(guild_id),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Выберите расписание для удаления:",
                view=ScheduleManagementView(guild_id),
                ephemeral=True
            )

    @discord.ui.button(label="📋 Пресет-лист", style=ButtonStyle.secondary, custom_id="preset_list")
    async def preset_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        memory.last_member_list[guild_id] = interaction.guild.members
        if interaction.response.is_done():
            await interaction.followup.send(
                "📋 Выберите до 6 участников для пресет-группы:",
                view=PresetSelectView(guild_id),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "📋 Выберите до 6 участников для пресет-группы:",
                view=PresetSelectView(guild_id),
                ephemeral=True
            )

    @discord.ui.button(label="👑 Добавить лидера", style=ButtonStyle.success, custom_id="add_leader")
    async def add_leader(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        if not memory.presets.get(guild_id, []):
            if interaction.response.is_done():
                await interaction.followup.send("Нет пресетов для выбора лидеров.", ephemeral=True)
            else:
                await interaction.response.send_message("Нет пресетов для выбора лидеров.", ephemeral=True)
            return
        memory.last_member_list[guild_id] = interaction.guild.members
        if interaction.response.is_done():
            await interaction.followup.send(
                "Выберите лидеров для каждой группы:",
                view=LeaderSelectionView(guild_id),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Выберите лидеров для каждой группы:",
                view=LeaderSelectionView(guild_id),
                ephemeral=True
            )

    @discord.ui.button(label="✏️ Редактировать пресет-группы", style=ButtonStyle.secondary, custom_id="edit_presets")
    async def edit_presets(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        if not memory.presets.get(guild_id, []):
            if interaction.response.is_done():
                await interaction.followup.send("Нет пресетов для редактирования.", ephemeral=True)
            else:
                await interaction.response.send_message("Нет пресетов для редактирования.", ephemeral=True)
            return
        memory.last_member_list[guild_id] = interaction.guild.members
        if interaction.response.is_done():
            await interaction.followup.send(
                "Выберите группу для редактирования:",
                view=EditPresetsView(guild_id),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Выберите группу для редактирования:",
                view=EditPresetsView(guild_id),
                ephemeral=True
            )