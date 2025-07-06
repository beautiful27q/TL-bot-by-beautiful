from collections import defaultdict

class EventState:
    def __init__(self, preset_groups=None, guild_id=None):
        """
        preset_groups: список групп пресетов (по конкретной гильдии)
        guild_id: id Discord сервера (гильдии)
        """
        self.preset_groups = preset_groups if preset_groups is not None else []
        self.guild_id = guild_id  # Важно для мультисерверности!
        self.participants = set()
        self.declined = set()
        self.user_roles = {}  # user_id -> "танк"|"хил"|"дд"
        self.current_groups = []

    def set_preset_groups(self, preset_groups):
        self.preset_groups = preset_groups
        self.rebuild_groups()

    def set_user_role(self, user_id, role):
        self.user_roles[user_id] = role

    def join(self, user_id):
        self.participants.add(user_id)
        self.declined.discard(user_id)
        self.rebuild_groups()

    def leave(self, user_id):
        self.participants.discard(user_id)
        self.declined.discard(user_id)
        self.rebuild_groups()

    def decline(self, user_id):
        self.leave(user_id)
        self.declined.add(user_id)
        self.rebuild_groups()

    def is_in_group(self, user_id):
        return user_id in self.participants

    def get_declined_list(self):
        return list(self.declined)

    def _get_role(self, user_id):
        # "танк", "хил", "дд"
        return self.user_roles.get(user_id, "дд")

    def rebuild_groups(self):
        # Вся логика работает только с self.preset_groups, self.participants, self.user_roles
        # Всё это теперь всегда уникально для данного события (и гильдии)!
        preset_leaders = {}
        for g in self.preset_groups:
            leader = g.get('лидер')
            if leader is not None:
                members = set(g.get('члены', []))
                preset_leaders[leader] = members

        # user_to_leader: для каждого участника — кто его лидер (по пресету)
        user_to_leader = {}
        for user_id in self.participants:
            found = False
            for leader, members in preset_leaders.items():
                # Лидер всегда считается участником своей группы!
                if user_id == leader or user_id in members:
                    user_to_leader[user_id] = leader
                    found = True
                    break
            if not found:
                user_to_leader[user_id] = None

        # Только лидеры, которые реально участвуют
        active_leaders = [leader for leader in preset_leaders if leader in self.participants]

        groups = []
        used_users = set()

        for leader in active_leaders:
            group = {
                "лидер": leader,
                "танк": None,
                "хил": None,
                "дд1": None,
                "дд2": None,
                "дд3": None,
                "дд4": None,
            }
            role_slots = ["танк", "хил", "дд1", "дд2", "дд3", "дд4"]
            role_count = {"танк": 0, "хил": 0, "дд": 0}

            # preset_users: только те, кто реально участвует (и лидер если он в участниках)
            preset_users = [uid for uid in ([leader] + list(preset_leaders[leader])) if uid in self.participants]

            # --- Ставим лидера в слот его роли ---
            leader_role = self._get_role(leader)
            leader_slot_set = False
            for slot in role_slots:
                if self._slot_to_role(slot) == leader_role and group[slot] is None and role_count[leader_role] < self._max_role_count(leader_role):
                    group[slot] = leader
                    role_count[leader_role] += 1
                    used_users.add(leader)
                    leader_slot_set = True
                    break
            if not leader_slot_set:
                group["лидер"] = None  # Если не удалось поставить лидера (нет подходящего слота)

            # --- Добавляем остальных участников пресета ---
            for member in preset_users:
                if member == leader:
                    continue
                member_role = self._get_role(member)
                for slot in role_slots:
                    if group[slot] is None and self._slot_to_role(slot) == member_role and role_count[member_role] < self._max_role_count(member_role):
                        group[slot] = member
                        role_count[member_role] += 1
                        used_users.add(member)
                        break

            # --- Заполняем оставшиеся слоты участниками, не входящими в preset, но с тем же лидером ---
            for slot in role_slots:
                if group[slot] is None:
                    for user_id in self.participants:
                        if user_id in used_users:
                            continue
                        if user_to_leader[user_id] == leader:
                            continue
                        user_role = self._get_role(user_id)
                        if self._slot_to_role(slot) == user_role and role_count[user_role] < self._max_role_count(user_role):
                            group[slot] = user_id
                            role_count[user_role] += 1
                            used_users.add(user_id)
                            break
            groups.append(group)

        # Остальные (рандомы)
        remaining = [uid for uid in self.participants if uid not in used_users]
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
            role_slots = ["танк", "хил", "дд1", "дд2", "дд3", "дд4"]
            role_count = {"танк": 0, "хил": 0, "дд": 0}
            to_remove = set()
            for slot in role_slots:
                for user_id in remaining:
                    user_role = self._get_role(user_id)
                    if self._slot_to_role(slot) == user_role and group[slot] is None and role_count[user_role] < self._max_role_count(user_role):
                        group[slot] = user_id
                        role_count[user_role] += 1
                        to_remove.add(user_id)
                        break
            if not to_remove:
                # break if nobody was assigned (avoid infinite loop)
                break
            remaining = [uid for uid in remaining if uid not in to_remove]
            if any(group.get(slot) for slot in role_slots):
                groups.append(group)
        self.current_groups = groups

        # Always show at least one empty group if there are no participants/groups yet
        if not self.current_groups:
            self.current_groups = [{
                "лидер": None,
                "танк": None,
                "хил": None,
                "дд1": None,
                "дд2": None,
                "дд3": None,
                "дд4": None,
            }]

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

    def get_group_data(self):
        return self.current_groups

    def time_status(self):
        return "Время до начала"
    def event_datetime_str(self):
        return "Дата и время события"
    def event_status(self):
        return "Регистрация открыта"

# Экземпляр для тестов — в реальном коде EventState должен создаваться с нужными preset_groups и guild_id!
event_state = EventState()