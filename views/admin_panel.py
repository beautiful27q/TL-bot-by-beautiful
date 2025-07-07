import discord
from discord import ButtonStyle
from config import ALLOWED_ROLES
from storage.memory import memory
from storage.persist import save_presets, save_schedules
from views.create_event import CreateEventModal
from views.recurring_event import RecurringEventModal
from sync_presets import sync_presets_to_event_state
import datetime

# --- Preset Selection with Pagination and Persistent Selection ---
class PresetSelectView(discord.ui.View):
    def __init__(self, guild_id, page=0, selected_ids=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.page = page
        self.max_per_page = 25
        self.selected_ids = set(selected_ids) if selected_ids is not None else set()
        self.add_item(PresetMemberSelect(guild_id, page, self.selected_ids))
        member_list = memory.last_member_list.get(guild_id, [])
        used_ids = set(uid for group in memory.presets.get(guild_id, []) for uid in group)
        available_members = [m for m in member_list if not m.bot and m.id not in used_ids]
        total = len(available_members)
        if total > self.max_per_page:
            if page > 0:
                self.add_item(PresetPrevButton(guild_id, page, self.selected_ids))
            if (page + 1) * self.max_per_page < total:
                self.add_item(PresetNextButton(guild_id, page, self.selected_ids))
        if self.selected_ids:
            self.add_item(PresetConfirmButton(guild_id, self.selected_ids))

class PresetMemberSelect(discord.ui.Select):
    def __init__(self, guild_id, page, selected_ids):
        self.guild_id = guild_id
        self.page = page
        self.max_per_page = 25
        self.selected_ids = set(selected_ids)
        used_ids = set(uid for group in memory.presets.get(guild_id, []) for uid in group)
        member_list = memory.last_member_list.get(guild_id, [])
        available_members = [m for m in member_list if not m.bot and m.id not in used_ids]
        start = page * self.max_per_page
        end = start + self.max_per_page
        page_members = available_members[start:end]
        remaining = max(0, 6 - len(self.selected_ids))
        options = [
            discord.SelectOption(
                label=member.name,
                value=str(member.id),
                default=(member.id in self.selected_ids)
            )
            for member in page_members
        ]
        super().__init__(
            placeholder="Выберите до 6 участников для пресет-группы (выбор сохраняется между страницами)",
            min_values=0,
            max_values=min(remaining + len([m.id for m in page_members if m.id in self.selected_ids]), len(options)),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        member_list = memory.last_member_list.get(guild_id, [])
        used_ids = set(uid for group in memory.presets.get(guild_id, []) for uid in group)
        available_members = [m for m in member_list if not m.bot and m.id not in used_ids]
        start = self.page * self.max_per_page
        end = start + self.max_per_page
        page_members = available_members[start:end]
        page_ids = set(m.id for m in page_members)
        new_selected = set(int(uid) for uid in self.values)
        selected_ids = set(self.selected_ids)
        selected_ids -= page_ids
        selected_ids |= new_selected

        if len(selected_ids) > 6:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"⚠️ Можно выбрать не более 6 участников. Сейчас выбрано: {len(selected_ids)}.",
                    ephemeral=True, delete_after=10
                )
            else:
                await interaction.response.send_message(
                    f"⚠️ Можно выбрать не более 6 участников. Сейчас выбрано: {len(selected_ids)}.",
                    ephemeral=True, delete_after=10
                )
            await interaction.message.edit(view=PresetSelectView(guild_id, self.page, list(selected_ids)[:6]))
            return

        await interaction.response.edit_message(
            view=PresetSelectView(guild_id, self.page, selected_ids)
        )

class PresetPrevButton(discord.ui.Button):
    def __init__(self, guild_id, page, selected_ids):
        super().__init__(label="⬅️ Назад", style=discord.ButtonStyle.secondary)
        self.guild_id = guild_id
        self.page = page
        self.selected_ids = set(selected_ids)

    async def callback(self, interaction: discord.Interaction):
        memory.last_member_list[self.guild_id] = interaction.guild.members
        await interaction.response.edit_message(
            view=PresetSelectView(self.guild_id, self.page - 1, self.selected_ids)
        )

class PresetNextButton(discord.ui.Button):
    def __init__(self, guild_id, page, selected_ids):
        super().__init__(label="Вперёд ➡️", style=discord.ButtonStyle.secondary)
        self.guild_id = guild_id
        self.page = page
        self.selected_ids = set(selected_ids)

    async def callback(self, interaction: discord.Interaction):
        memory.last_member_list[self.guild_id] = interaction.guild.members
        await interaction.response.edit_message(
            view=PresetSelectView(self.guild_id, self.page + 1, self.selected_ids)
        )

class PresetConfirmButton(discord.ui.Button):
    def __init__(self, guild_id, selected_ids):
        super().__init__(label="✅ Подтвердить группу", style=discord.ButtonStyle.success, row=2)
        self.guild_id = guild_id
        self.selected_ids = set(selected_ids)

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        already_in_group = []
        for uid in self.selected_ids:
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
                    ephemeral=True, delete_after=10
                )
            else:
                await interaction.response.send_message(
                    f"❌ Эти участники уже состоят в других пресет-группах: {names}\n"
                    f"Удалите их из других групп перед добавлением.",
                    ephemeral=True, delete_after=10
                )
            return

        group_number = len(memory.presets.get(guild_id, [])) + 1
        new_group = list(self.selected_ids)
        memory.presets.setdefault(guild_id, []).append(new_group)
        save_presets(guild_id)
        sync_presets_to_event_state(guild_id)
        if interaction.response.is_done():
            await interaction.followup.send(
                f"✅ Добавлена пресет-группа {group_number} с {len(new_group)} участниками.",
                ephemeral=True, delete_after=10
            )
        else:
            await interaction.response.send_message(
                f"✅ Добавлена пресет-группа {group_number} с {len(new_group)} участниками.",
                ephemeral=True, delete_after=10
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
        # Только админ может назначить лидера
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            if interaction.response.is_done():
                await interaction.followup.send("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return

        if self.values[0] == "none":
            if interaction.response.is_done():
                await interaction.followup.send("Нет кандидатов для лидера.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Нет кандидатов для лидера.", ephemeral=True, delete_after=10)
            return
        user_id = int(self.values[0])
        if user_id not in memory.presets[guild_id][self.group_index]:
            for idx, group in enumerate(memory.presets[guild_id]):
                if idx != self.group_index and user_id in group:
                    if interaction.response.is_done():
                        await interaction.followup.send(
                            f"❌ Этот пользователь уже состоит в другой пресет-группе. Сначала удалите его из той группы.",
                            ephemeral=True, delete_after=10
                        )
                    else:
                        await interaction.response.send_message(
                            f"❌ Этот пользователь уже состоит в другой пресет-группе. Сначала удалите его из той группы.",
                            ephemeral=True, delete_after=10
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
                ephemeral=True, delete_after=10
            )
        else:
            await interaction.response.send_message(
                f"👑 Лидер для Группы {self.group_index + 1} назначен: {member.mention}",
                ephemeral=True, delete_after=10
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
        # Только админ может удалять расписание
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            if interaction.response.is_done():
                await interaction.followup.send("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return

        if self.values[0] == "none":
            if interaction.response.is_done():
                await interaction.followup.send("Нет событий для удаления.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Нет событий для удаления.", ephemeral=True, delete_after=10)
            return
        index = int(self.values[0])
        sched = memory.schedules[guild_id].pop(index)
        save_schedules(guild_id)
        msg_id = sched.get("message_id")
        ch_id = sched.get("channel_id")
        to_remove = None
        for event in getattr(memory, "active_events", {}).get(guild_id, []):
            if event.get("message_id") == msg_id and event.get("channel_id") == ch_id:
                to_remove = event
                break
        if to_remove:
            getattr(memory, "active_events", {}).get(guild_id, []).remove(to_remove)
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
            await interaction.followup.send("✅ Расписание и сообщение удалены.", ephemeral=False, delete_after=10)
        else:
            await interaction.response.send_message("✅ Расписание и сообщение удалены.", ephemeral=False, delete_after=10)

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
        # Только админ может редактировать группы
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            if interaction.response.is_done():
                await interaction.followup.send("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return

        if self.values[0] == "none":
            if interaction.response.is_done():
                await interaction.followup.send("Нет доступных групп.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Нет доступных групп.", ephemeral=True, delete_after=10)
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
                ephemeral=True, delete_after=10
            )
        else:
            await interaction.response.send_message(
                f"✏️ Редактирование группы {group_index + 1}:\n{group_text}",
                view=PresetMemberEditView(guild_id, group_index, group),
                ephemeral=True, delete_after=10
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
        # Только админ может менять участников группы
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            if interaction.response.is_done():
                await interaction.followup.send("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return

        if self.values[0] == "none":
            if interaction.response.is_done():
                await interaction.followup.send("Нет участников для изменения.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Нет участников для изменения.", ephemeral=True, delete_after=10)
            return
        user_id = int(self.values[0])
        if interaction.response.is_done():
            await interaction.followup.send(
                f"Участник выбран: <@{user_id}>. Выберите действие:",
                view=PresetMemberActionView(guild_id, self.group_index, user_id),
                ephemeral=True, delete_after=10
            )
        else:
            await interaction.response.send_message(
                f"Участник выбран: <@{user_id}>. Выберите действие:",
                view=PresetMemberActionView(guild_id, self.group_index, user_id),
                ephemeral=True, delete_after=10
            )

class PresetMemberActionView(discord.ui.View):
    def __init__(self, guild_id, group_index, user_id):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.group_index = group_index
        self.user_id = user_id

    @discord.ui.button(label="❌ Удалить из группы", style=discord.ButtonStyle.danger)
    async def remove_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Только админ может удалять участников
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            if interaction.response.is_done():
                await interaction.followup.send("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return

        guild_id = interaction.guild.id
        group = memory.presets[guild_id][self.group_index]
        if self.user_id in group:
            group.remove(self.user_id)
            if memory.group_leaders.get(guild_id, {}).get(self.group_index) == self.user_id:
                memory.group_leaders[guild_id][self.group_index] = None
            save_presets(guild_id)
            sync_presets_to_event_state(guild_id)
            if interaction.response.is_done():
                await interaction.followup.send(f"Участник <@{self.user_id}> удалён из группы.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message(f"Участник <@{self.user_id}> удалён из группы.", ephemeral=True, delete_after=10)
        else:
            if interaction.response.is_done():
                await interaction.followup.send("Участник не найден в группе.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Участник не найден в группе.", ephemeral=True, delete_after=10)

    @discord.ui.button(label="➡️ Переместить в другую группу", style=discord.ButtonStyle.primary)
    async def move_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Только админ может перемещать участников
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            if interaction.response.is_done():
                await interaction.followup.send("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return

        guild_id = interaction.guild.id
        count = len(memory.presets.get(guild_id, []))
        options = []
        for i in range(count):
            if i != self.group_index:
                options.append(discord.SelectOption(label=f"Группа {i+1}", value=str(i)))
        if not options:
            if interaction.response.is_done():
                await interaction.followup.send("Нет других групп для перемещения.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Нет других групп для перемещения.", ephemeral=True, delete_after=10)
            return
        if interaction.response.is_done():
            await interaction.followup.send(
                "Выберите целевую группу:",
                view=PresetMemberMoveTargetView(guild_id, self.group_index, self.user_id, options),
                ephemeral=True, delete_after=10
            )
        else:
            await interaction.response.send_message(
                "Выберите целевую группу:",
                view=PresetMemberMoveTargetView(guild_id, self.group_index, self.user_id, options),
                ephemeral=True, delete_after=10
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
        # Только админ может перемещать участников
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            if interaction.response.is_done():
                await interaction.followup.send("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return

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
                        ephemeral=True, delete_after=10
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ Этот пользователь уже состоит в другой пресет-группе. Сначала удалите его из той группы.",
                        ephemeral=True, delete_after=10
                    )
                return
        if self.user_id not in to_group:
            to_group.append(self.user_id)
        save_presets(guild_id)
        sync_presets_to_event_state(guild_id)
        if interaction.response.is_done():
            await interaction.followup.send(
                f"Участник <@{self.user_id}> перемещён в группу {to_group_index+1}.",
                ephemeral=True, delete_after=10
            )
        else:
            await interaction.response.send_message(
                f"Участник <@{self.user_id}> перемещён в группу {to_group_index+1}.",
                ephemeral=True, delete_after=10
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
        # Только админ может удалять группы
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            if interaction.response.is_done():
                await interaction.followup.send("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return

        guild_id = interaction.guild.id
        if 0 <= self.group_index < len(memory.presets.get(guild_id, [])):
            memory.presets[guild_id].pop(self.group_index)
            if self.group_index in memory.group_leaders.get(guild_id, {}):
                del memory.group_leaders[guild_id][self.group_index]
            memory.group_leaders[guild_id] = {i if i < self.group_index else i-1: lid for i, lid in memory.group_leaders[guild_id].items() if i != self.group_index}
            save_presets(guild_id)
            sync_presets_to_event_state(guild_id)
            if interaction.response.is_done():
                await interaction.followup.send("Группа удалена.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Группа удалена.", ephemeral=True, delete_after=10)
        else:
            if interaction.response.is_done():
                await interaction.followup.send("Группа не найдена.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Группа не найдена.", ephemeral=True, delete_after=10)

class AdminPanelView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="🗓 Создать событие", style=ButtonStyle.primary, custom_id="create_event_modal")
    async def create_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return
        await interaction.response.send_modal(CreateEventModal())

    @discord.ui.button(label="🔁 Повторяющееся событие", style=ButtonStyle.secondary, custom_id="create_schedule")
    async def create_schedule(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return
        await interaction.response.send_modal(RecurringEventModal())

    @discord.ui.button(label="⚙️ Изменить повторяющееся событие", style=ButtonStyle.danger, custom_id="edit_schedule")
    async def edit_schedule(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return
        guild_id = interaction.guild.id
        if not memory.schedules.get(guild_id, []):
            if interaction.response.is_done():
                await interaction.followup.send("Нет активных расписаний.", ephemeral=False, delete_after=10)
            else:
                await interaction.response.send_message("Нет активных расписаний.", ephemeral=False, delete_after=10)
            return
        if interaction.response.is_done():
            await interaction.followup.send(
                "Выберите расписание для удаления:",
                view=ScheduleManagementView(guild_id),
                ephemeral=False,
                delete_after=30
            )
        else:
            await interaction.response.send_message(
                "Выберите расписание для удаления:",
                view=ScheduleManagementView(guild_id),
                ephemeral=False,
                delete_after=30
            )

    @discord.ui.button(label="📋 Пресет-лист", style=ButtonStyle.secondary, custom_id="preset_list")
    async def preset_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return
        guild_id = interaction.guild.id
        memory.last_member_list[guild_id] = interaction.guild.members
        if interaction.response.is_done():
            await interaction.followup.send(
                "📋 Выберите до 6 участников для пресет-группы:",
                view=PresetSelectView(guild_id),
                ephemeral=True, delete_after=300
            )
        else:
            await interaction.response.send_message(
                "📋 Выберите до 6 участников для пресет-группы:",
                view=PresetSelectView(guild_id),
                ephemeral=True, delete_after=300
            )

    @discord.ui.button(label="👑 Добавить лидера", style=ButtonStyle.success, custom_id="add_leader")
    async def add_leader(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return
        guild_id = interaction.guild.id
        if not memory.presets.get(guild_id, []):
            if interaction.response.is_done():
                await interaction.followup.send("Нет пресетов для выбора лидеров.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Нет пресетов для выбора лидеров.", ephemeral=True, delete_after=10)
            return
        memory.last_member_list[guild_id] = interaction.guild.members
        if interaction.response.is_done():
            await interaction.followup.send(
                "Выберите лидеров для каждой группы:",
                view=LeaderSelectionView(guild_id),
                ephemeral=True, delete_after=180
            )
        else:
            await interaction.response.send_message(
                "Выберите лидеров для каждой группы:",
                view=LeaderSelectionView(guild_id),
                ephemeral=True, delete_after=180
            )

    @discord.ui.button(label="✏️ Редактировать пресет-группы", style=ButtonStyle.secondary, custom_id="edit_presets")
    async def edit_presets(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.name in ALLOWED_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("⛔ У тебя нет прав доступа.", ephemeral=True, delete_after=10)
            return
        guild_id = interaction.guild.id
        if not memory.presets.get(guild_id, []):
            if interaction.response.is_done():
                await interaction.followup.send("Нет пресетов для редактирования.", ephemeral=True, delete_after=10)
            else:
                await interaction.response.send_message("Нет пресетов для редактирования.", ephemeral=True, delete_after=10)
            return
        memory.last_member_list[guild_id] = interaction.guild.members
        if interaction.response.is_done():
            await interaction.followup.send(
                "Выберите группу для редактирования:",
                view=EditPresetsView(guild_id),
                ephemeral=True, delete_after=300
            )
        else:
            await interaction.response.send_message(
                "Выберите группу для редактирования:",
                view=EditPresetsView(guild_id),
                ephemeral=True, delete_after=300
            )