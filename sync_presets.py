from storage.memory import memory, active_events  # Исправленный импорт

def sync_presets_to_event_state(guild_id=None):
    """
    Распределяет пресеты и лидеров по всем активным событиям с сохранением рандомов.
    - Лидер и его пресет всегда в своей группе и занимают свои ролевые слоты.
    - Пресетные участники вытесняют рандомов из тех же слотов.
    - Если слот в группе после расстановки пресета пуст, туда возвращается рандом из старой группы.
    - Количество групп — как в пресетах.
    Если guild_id не указан — синхронизирует для всех гильдий.
    """
    target_guilds = [guild_id] if guild_id is not None else list(active_events.keys())
    for g_id in target_guilds:
        for event in active_events.get(g_id, []):
            event_state = event["event_state"]
            old_groups = event_state.groups if hasattr(event_state, "groups") else []
            new_groups = []

            presets = memory.presets.get(g_id, [])
            group_leaders = memory.group_leaders.get(g_id, {})
            user_roles = memory.user_roles.get(g_id, {})

            for idx, group in enumerate(presets):
                leader = group_leaders.get(idx)
                group_set = set(group)
                members = list(group_set)

                # Начинаем собирать новую группу с пресетными ролями
                group_dict = {
                    "лидер": leader,
                    "танк": None,
                    "хил": None,
                    "дд1": None,
                    "дд2": None,
                    "дд3": None,
                    "дд4": None
                }
                dd_slots = ["дд1", "дд2", "дд3", "дд4"]

                # 1. Сначала расставляем участников из пресета по их ролям (и лидера тоже)
                for uid in members:
                    role = user_roles.get(uid)
                    if role == "танк" and group_dict["танк"] is None:
                        group_dict["танк"] = uid
                    elif role == "хил" and group_dict["хил"] is None:
                        group_dict["хил"] = uid
                    elif role == "дд":
                        for dd_slot in dd_slots:
                            if group_dict[dd_slot] is None:
                                group_dict[dd_slot] = uid
                                break

                # 2. Затем для пустых слотов ищем "рандомов" из старой группы (если есть)
                if idx < len(old_groups):
                    old_group = old_groups[idx]
                    # Проверяем все ролевые слоты, если они не заняты пресетом — ищем рандома
                    # Танк
                    if group_dict["танк"] is None:
                        old_uid = old_group.get("танк")
                        if old_uid and old_uid not in members:
                            group_dict["танк"] = old_uid
                    # Хил
                    if group_dict["хил"] is None:
                        old_uid = old_group.get("хил")
                        if old_uid and old_uid not in members:
                            group_dict["хил"] = old_uid
                    # ДД
                    for dd_slot in dd_slots:
                        if group_dict[dd_slot] is None:
                            old_uid = old_group.get(dd_slot)
                            if old_uid and old_uid not in members and old_uid not in group_dict.values():
                                group_dict[dd_slot] = old_uid

                new_groups.append(group_dict)

            # Обрезаем лишние старые группы, если пресетов стало меньше
            event_state.groups = new_groups