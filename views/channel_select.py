import discord

class ChannelSelectView(discord.ui.View):
    def __init__(self, bot, callback):
        super().__init__(timeout=60)
        self.bot = bot
        self.callback_func = callback
        self.guild = None  # guild будет определяться при первом использовании
        self.options = []

    async def setup(self, guild):
        self.guild = guild
        options = [
            discord.SelectOption(label=ch.name, value=str(ch.id))
            for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages
        ]
        # Обновляем/пересоздаём select (удаляем старый если был)
        for item in self.children:
            self.remove_item(item)
        self.add_item(ChannelSelect(options, self.callback_func))

class ChannelSelect(discord.ui.Select):
    def __init__(self, options, callback_func):
        super().__init__(placeholder="Выберите канал для события", options=options)
        self.callback_func = callback_func

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        await self.callback_func(interaction, channel_id)