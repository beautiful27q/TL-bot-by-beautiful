# storage/memory.py

class Memory:
    def __init__(self):
        self.presets = {}        # {guild_id: [[...], ...]}
        self.group_leaders = {}  # {guild_id: {group_idx: user_id}}
        self.user_roles = {}     # {guild_id: {user_id: "role"}}
        self.schedules = {}      # {guild_id: [...]}
        self.last_member_list = {}  # {guild_id: [...]}

memory = Memory()

# Главный контейнер для событий: {guild_id: [event_dict, ...]}
active_events = {}

# --- EventState не меняется, но теперь каждый event_state относится к своей гильдии! ---
class EventState:
    def __init__(self):
        self.groups = [
            {"лидер": None, "танк": None, "хил": None, "дд1": None, "дд2": None, "дд3": None, "дд4": None}
        ]
        self.declined_users = set()
        self.user_roles = {}  # {user_id: "танк"/"хил"/"дд"} — только реально участвующие!

    def _remove_from_all_slots(self, user_id):
        for group in self.groups:
            for slot, uid in group.items():
                if uid == user_id:
                    group[slot] = None

    def regroup_presets_without_leader(self, min_group_size=4, guild_id=None):
        # guild_id обязателен для мультисерверной логики!
        if guild_id is None:
            raise Exception("guild_id must be provided for regroup_presets_without_leader")
        used_uids = set()
        for group in self.groups:
            for slot, uid in group.items():
                if uid:
                    used_uids.add(uid)

        for idx, preset in enumerate(memory.presets.get(guild_id, [])):
            leader_id = memory.group_leaders.get(guild_id, {}).get(idx)
            present = [uid for uid in preset if uid in self.user_roles]
            leader_in_event = leader_id and leader_id in self.user_roles
            if len(present) >= min_group_size and not leader_in_event:
                found_group = None
                for group in self.groups:
                    if all(uid in group.values() for uid in present):
                        found_group = group
                        break
                if found_group:
                    continue
                for uid in present:
                    self._remove_from_all_slots(uid)
                group = None
                for g in self.groups:
                    if all(v is None for k, v in g.items() if k != "лидер"):
                        group = g
                        break
                if not group:
                    group = {"лидер": None, "танк": None, "хил": None,
                             "дд1": None, "дд2": None, "дд3": None, "дд4": None}
                    self.groups.append(group)
                for uid in present:
                    role = self.user_roles[uid]
                    if role == "танк" and not group["танк"]:
                        group["танк"] = uid
                    elif role == "хил" and not group["хил"]:
                        group["хил"] = uid
                    elif role == "дд":
                        for dd_slot in ("дд1", "дд2", "дд3", "дд4"):
                            if not group[dd_slot]:
                                group[dd_slot] = uid
                                break
                used = set(uid for uid in group.values() if uid)
                for role in ["танк", "хил", "дд1", "дд2", "дд3", "дд4"]:
                    if not group[role]:
                        for g in self.groups:
                            for slot, uid in g.items():
                                if uid and uid not in preset and uid not in used:
                                    group[role] = uid
                                    used.add(uid)
                                    g[slot] = None
                                    break
                            if group[role]:
                                break

    def join(self, user_id, guild_id=None):
        if guild_id is None:
            raise Exception("guild_id must be provided for join")
        self._remove_from_all_slots(user_id)
        self.declined_users.discard(user_id)
        role = self.user_roles.get(user_id)
        if not role:
            return

        user_preset_idx = None
        for idx, group in enumerate(memory.presets.get(guild_id, [])):
            if user_id in group:
                user_preset_idx = idx
                break

        if user_preset_idx is not None and memory.group_leaders.get(guild_id, {}).get(user_preset_idx) == user_id:
            preset_members = [uid for uid in memory.presets[guild_id][user_preset_idx] if uid != user_id and uid in self.user_roles]
            for member in preset_members:
                self._remove_from_all_slots(member)
            if user_preset_idx < len(self.groups):
                group = self.groups[user_preset_idx]
                for k in group: group[k] = None
            else:
                group = {"лидер": None, "танк": None, "хил": None, "дд1": None, "дд2": None, "дд3": None, "дд4": None}
                while len(self.groups) <= user_preset_idx:
                    self.groups.append({"лидер": None, "танк": None, "хил": None, "дд1": None, "дд2": None, "дд3": None, "дд4": None})
                self.groups[user_preset_idx] = group
            group["лидер"] = user_id
            if role == "танк":
                group["танк"] = user_id
            elif role == "хил":
                group["хил"] = user_id
            elif role == "дд":
                for dd_slot in ("дд1", "дд2", "дд3", "дд4"):
                    if group[dd_slot] is None:
                        group[dd_slot] = user_id
                        break
            for member in preset_members:
                m_role = self.user_roles.get(member)
                if m_role == "танк" and group["танк"] is None:
                    group["танк"] = member
                elif m_role == "хил" and group["хил"] is None:
                    group["хил"] = member
                elif m_role == "дд":
                    for dd_slot in ("дд1", "дд2", "дд3", "дд4"):
                        if group[dd_slot] is None:
                            group[dd_slot] = member
                            break
            return

        if user_preset_idx is not None:
            leader_id = memory.group_leaders.get(guild_id, {}).get(user_preset_idx)
            leader_in_event = False
            target_group = None
            for group in self.groups:
                if group["лидер"] == leader_id:
                    leader_in_event = True
                    target_group = group
                    break
            if leader_in_event and target_group:
                if role == "танк" and target_group["танк"] is None:
                    target_group["танк"] = user_id
                    return
                elif role == "хил" and target_group["хил"] is None:
                    target_group["хил"] = user_id
                    return
                elif role == "дд":
                    for dd_slot in ("дд1", "дд2", "дд3", "дд4"):
                        if target_group[dd_slot] is None:
                            target_group[dd_slot] = user_id
                            return

        for group in self.groups:
            if role == "дд":
                for dd_slot in ("дд1", "дд2", "дд3", "дд4"):
                    if group[dd_slot] is None:
                        group[dd_slot] = user_id
                        self.regroup_presets_without_leader(guild_id=guild_id)
                        return
            else:
                if group[role] is None:
                    group[role] = user_id
                    self.regroup_presets_without_leader(guild_id=guild_id)
                    return
        new_group = {"лидер": None, "танк": None, "хил": None, "дд1": None, "дд2": None, "дд3": None, "дд4": None}
        if role == "дд":
            new_group["дд1"] = user_id
        else:
            new_group[role] = user_id
        self.groups.append(new_group)
        self.regroup_presets_without_leader(guild_id=guild_id)

    def leave(self, user_id, guild_id=None):
        if guild_id is None:
            raise Exception("guild_id must be provided for leave")
        self._remove_from_all_slots(user_id)
        self.regroup_presets_without_leader(guild_id=guild_id)
        if user_id in self.user_roles:
            del self.user_roles[user_id]

    def decline(self, user_id, guild_id=None):
        if guild_id is None:
            raise Exception("guild_id must be provided for decline")
        self.declined_users.add(user_id)
        self.leave(user_id, guild_id=guild_id)

    def set_user_role(self, user_id, role):
        self.user_roles[user_id] = role
        # memory.user_roles не трогаем здесь — только для !роль и RoleSelectView

    def change_user_role(self, user_id, new_role, guild_id=None):
        if guild_id is None:
            raise Exception("guild_id must be provided for change_user_role")
        self.leave(user_id, guild_id=guild_id)
        self.set_user_role(user_id, new_role)
        self.join(user_id, guild_id=guild_id)

    def set_leader(self, group_index, user_id):
        if 0 <= group_index < len(self.groups):
            self.groups[group_index]["лидер"] = user_id

    def get_declined_list(self):
        return list(self.declined_users)

    def get_group_data(self):
        return self.groups