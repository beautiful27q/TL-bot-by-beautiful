# storage/memory.py

class Memory:
    def __init__(self):
        self.presets = {}
        self.group_leaders = {}
        self.user_roles = {}
        self.schedules = {}
        self.last_member_list = {}

memory = Memory()

active_events = {}

class EventState:
    def __init__(self):
        self.groups = [
            {"лидер": None, "танк": None, "хил": None, "дд1": None, "дд2": None, "дд3": None, "дд4": None}
        ]
        self.declined_users = set()
        self.user_roles = {}

    def _slot_to_role(self, slot):
        if slot == "танк":
            return "танк"
        if slot == "хил":
            return "хил"
        return "дд"

    def _max_role_count(self, role):
        if role == "танк":
            return 1
        if role == "хил":
            return 1
        return 4

    def set_user_role(self, user_id, role):
        self.user_roles[user_id] = role

    def join(self, user_id, guild_id=None):
        if guild_id is None:
            raise Exception("guild_id must be provided for join")
        self.declined_users.discard(user_id)
        if user_id not in self.user_roles:
            return
        self._rebuild_groups(guild_id)

    def leave(self, user_id, guild_id=None):
        if guild_id is None:
            raise Exception("guild_id must be provided for leave")
        # self.declined_users.discard(user_id)  # <-- УДАЛИТЬ ЭТУ СТРОКУ!
        self.user_roles.pop(user_id, None)
        self._rebuild_groups(guild_id)

    def decline(self, user_id, guild_id=None):
        if guild_id is None:
            raise Exception("guild_id must be provided for decline")
        self.declined_users.add(user_id)
        self.leave(user_id, guild_id=guild_id)

    def change_user_role(self, user_id, new_role, guild_id=None):
        if guild_id is None:
            raise Exception("guild_id must be provided for change_user_role")
        self.set_user_role(user_id, new_role)
        self._rebuild_groups(guild_id)

    def set_leader(self, group_index, user_id):
        if 0 <= group_index < len(self.groups):
            self.groups[group_index]["лидер"] = user_id

    def get_declined_list(self):
        return list(self.declined_users)

    def get_group_data(self):
        return self.groups

    def _rebuild_groups(self, guild_id):
        all_participants = set(self.user_roles) - set(self.declined_users)
        presets = memory.presets.get(guild_id, [])
        group_leaders = memory.group_leaders.get(guild_id, {})
        participants_roles = {uid: self.user_roles[uid] for uid in all_participants}

        leader_to_groupidx = {v: k for k, v in group_leaders.items()}
        preset_groups = []
        for idx, preset in enumerate(presets):
            leader = group_leaders.get(idx)
            if leader is None:
                continue
            preset_users = [uid for uid in preset if uid in all_participants]
            leader_in = leader in all_participants
            if leader_in or preset_users:
                preset_groups.append({"idx": idx, "leader": leader, "members": preset_users})

        used_users = set()
        groups = []

        for grp in preset_groups:
            leader = grp["leader"]
            members = grp["members"]
            group = {
                "лидер": leader if leader in all_participants else None,
                "танк": None,
                "хил": None,
                "дд1": None,
                "дд2": None,
                "дд3": None,
                "дд4": None,
            }
            role_slots = ["танк", "хил", "дд1", "дд2", "дд3", "дд4"]
            role_count = {"танк": 0, "хил": 0, "дд": 0}
            used_in_this_group = set()
            if leader in all_participants:
                l_role = participants_roles[leader]
                for slot in role_slots:
                    if self._slot_to_role(slot) == l_role and group[slot] is None and role_count[l_role] < self._max_role_count(l_role):
                        group[slot] = leader
                        role_count[l_role] += 1
                        used_users.add(leader)
                        used_in_this_group.add(leader)
                        break
            for member in members:
                if member == leader:
                    continue
                m_role = participants_roles[member]
                for slot in role_slots:
                    if (
                        group[slot] is None and
                        self._slot_to_role(slot) == m_role and
                        role_count[m_role] < self._max_role_count(m_role) and
                        member not in used_in_this_group
                    ):
                        group[slot] = member
                        role_count[m_role] += 1
                        used_users.add(member)
                        used_in_this_group.add(member)
                        break
            groups.append(group)

        remaining = [uid for uid in all_participants if uid not in used_users]

        role_slots = ["танк", "хил", "дд1", "дд2", "дд3", "дд4"]
        for group in groups:
            role_count = {
                "танк": int(group["танк"] is not None),
                "хил": int(group["хил"] is not None),
                "дд": sum(group[slot] is not None for slot in ["дд1", "дд2", "дд3", "дд4"])
            }
            to_remove = set()
            used_in_this_group = set(uid for uid in group.values() if uid is not None)
            for slot in role_slots:
                if group[slot] is not None:
                    continue
                for uid in remaining:
                    if uid in used_in_this_group:
                        continue
                    role = participants_roles[uid]
                    if self._slot_to_role(slot) == role and role_count[role] < self._max_role_count(role):
                        group[slot] = uid
                        role_count[role] += 1
                        to_remove.add(uid)
                        used_in_this_group.add(uid)
                        break
            remaining = [uid for uid in remaining if uid not in to_remove]

        while remaining:
            group = {
                "лидер": None,
                "танк": None,
                "хил": None,
                "дд1": None,
                "дд2": None,
                "дд3": None,
                "дд4": None,
            }
            role_count = {"танк": 0, "хил": 0, "дд": 0}
            to_remove = set()
            used_in_this_group = set()
            for slot in role_slots:
                for uid in remaining:
                    if uid in used_in_this_group:
                        continue
                    role = participants_roles[uid]
                    if self._slot_to_role(slot) == role and role_count[role] < self._max_role_count(role):
                        group[slot] = uid
                        role_count[role] += 1
                        to_remove.add(uid)
                        used_in_this_group.add(uid)
                        break
            if any(group[slot] for slot in role_slots):
                groups.append(group)
            remaining = [uid for uid in remaining if uid not in to_remove]

        if not groups:
            groups = [{
                "лидер": None,
                "танк": None,
                "хил": None,
                "дд1": None,
                "дд2": None,
                "дд3": None,
                "дд4": None,
            }]
        self.groups = groups