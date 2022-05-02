import asyncio
import datetime
import logging

import discord
from redbot.core.data_manager import cog_data_path
from redbot.core import commands

from .event_storage import EventStorage

log = logging.getLogger("red.kenku")


class EventManager:
    def __init__(self, cog: commands.Cog):
        self.cog = cog

        path = cog_data_path(cog_instance=cog)
        self.storage = EventStorage(path)
        self.storage.initialize()

        self.active_task = None

    def rescan_channel(
        self, ctx: commands.Context, channel: discord.TextChannel, handler
    ):
        self.active_task = asyncio.create_task(self._rescan_task(ctx, channel, handler))

    async def _rescan_task(
        self, ctx: commands.Context, channel: discord.TextChannel, handler
    ):
        async with ctx.typing():
            await asyncio.sleep(1.0)
            status_message: discord.Message = await ctx.send(
                f"⏳ Scan task started. Watch this space..."
            )

            # scan channel history (how far back?)
            count = 0
            flip = False
            async for message in channel.history(limit=1000):
                await handler(message)

                count += 1
                if count % 100 == 0:
                    await asyncio.sleep(2.0)
                    emoji = "🎶" if flip else "🎵"
                    flip = not flip
                    await status_message.edit(
                        content=f"{emoji} Scanned {count} messages so far..."
                    )

            await status_message.edit(content=f"🏁 Scan complete. Checked {count} messages.")
            self.active_task = None

    def _default_season(self, guild_id):
        # FUTURE: multi-season support; for now just use the first/default
        seasons = self.storage.get_seasons(guild_id=guild_id)
        if len(seasons) > 0:
            return seasons[0]
        else:
            self.storage.configure_season(
                name="Season 1", guild_id=guild_id, start_at=datetime.datetime.now()
            )
            seasons = self.storage.get_seasons(guild_id=guild_id)
            return seasons[0]

    def configure_channel(self, channel: discord.TextChannel, point_value: int = None):
        season_id = self._default_season(channel.guild.id)["id"]

        if point_value == 0:
            self.storage.remove_channel(season_id=season_id, channel_id=channel.id)
            return

        self.storage.configure_channel(
            season_id=season_id, channel_id=channel.id, point_value=point_value
        )
        self.storage.update_snowflake(id=channel.id, name=channel.name)

    def clear_channel_points(self, channel: discord.TextChannel):
        self.storage.clear_channel_points(channel_id=channel.id)
    
    def get_season_channels(self, ctx: commands.Context):
        season = self._default_season(ctx.guild.id)
        return season, self.storage.get_season_channels(season["id"])

    def add_point(self, message: discord.Message):
        season_id = self._default_season(message.guild.id)["id"]
        self.storage.record_point(
            message_id=message.id,
            user_id=message.author.id,
            season_id=season_id,
            channel_id=message.channel.id,
            sent_at=message.created_at,
        )
        self.storage.update_snowflake(
            id=message.author.id,
            name=f"{message.author.name}#{message.author.discriminator}",
        )
        self.storage.update_snowflake(id=message.channel.id, name=message.channel.name)

    def remove_point(self, message: discord.Message):
        season_id = self._default_season(message.guild.id)["id"]
        self.storage.remove_point(
            message_id=message.id, season_id=season_id, user_id=message.author.id
        )

    def user_info(self, user: discord.Member):
        season = self._default_season(user.guild.id)

        points = self.storage.get_points_for_user(
            season_id=season["id"], user_id=user.id
        )
        point_map = {}
        for point in points:
            channel_id = point["channel_id"]
            current_points = point_map.get(channel_id, 0)
            point_map[channel_id] = current_points + point["point_value"]
        return season, point_map

    def compute_leaderboard(self, guild_id):
        season = self._default_season(guild_id)

        sorted_scores = self.storage.get_season_scores(season_id=season["id"])
        score_map = {s["user_id"]: s["score"] for s in sorted_scores}
        return season, score_map

    def debug(self):
        data = self.storage.export()
        if len(data) == 0:
            return []
        return [data[0].keys()] + [tuple(row) for row in data]
