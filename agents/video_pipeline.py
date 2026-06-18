"""
Video Pipeline Agent
Pulls YouTube channel stats + last 5 video performance via YouTube Data API v3.
Requires: YOUTUBE_API_KEY, YOUTUBE_CHANNEL_ID
"""
import os
import requests
import memory_store


class VideoPipelineAgent:
    name = "video_pipeline"
    YT_BASE = "https://www.googleapis.com/youtube/v3"

    def run(self) -> str:
        try:
            api_key = os.getenv("YOUTUBE_API_KEY")
            channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
            if not api_key or not channel_id:
                return self._no_creds()
            return self._fetch(api_key, channel_id)
        except Exception as e:
            msg = f"Video Pipeline Agent error: {e}"
            memory_store.update_agent(self.name, msg)
            return msg

    def _fetch(self, api_key: str, channel_id: str) -> str:
        channel = self._channel_stats(api_key, channel_id)
        stats = channel["statistics"]
        subs = int(stats.get("subscriberCount", 0))
        views = int(stats.get("viewCount", 0))
        videos_total = int(stats.get("videoCount", 0))

        recent = self._recent_videos(api_key, channel_id)
        lines = [
            f"VIDEO PIPELINE",
            f"  Subscribers: {subs:,}",
            f"  Total views: {views:,}",
            f"  Total videos: {videos_total}",
            f"  Recent uploads:",
        ]
        for v in recent[:5]:
            vstats = v.get("statistics", {})
            v_views = int(vstats.get("viewCount", 0))
            likes = int(vstats.get("likeCount", 0))
            title = v["snippet"]["title"][:50]
            lines.append(f"    • {title} — {v_views:,} views, {likes:,} likes")

        summary = "\n".join(lines)
        memory_store.update_agent(
            self.name,
            summary,
            {"subscribers": subs, "total_views": views, "recent_count": len(recent)},
        )
        return summary

    def _channel_stats(self, api_key: str, channel_id: str) -> dict:
        resp = requests.get(
            f"{self.YT_BASE}/channels",
            params={"part": "statistics,snippet", "id": channel_id, "key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            raise ValueError(f"No channel found for ID: {channel_id}")
        return items[0]

    def _recent_videos(self, api_key: str, channel_id: str) -> list:
        search_resp = requests.get(
            f"{self.YT_BASE}/search",
            params={
                "part": "id",
                "channelId": channel_id,
                "order": "date",
                "maxResults": 5,
                "type": "video",
                "key": api_key,
            },
            timeout=15,
        )
        search_resp.raise_for_status()
        video_ids = [i["id"]["videoId"] for i in search_resp.json().get("items", [])]
        if not video_ids:
            return []

        stats_resp = requests.get(
            f"{self.YT_BASE}/videos",
            params={
                "part": "statistics,snippet",
                "id": ",".join(video_ids),
                "key": api_key,
            },
            timeout=15,
        )
        stats_resp.raise_for_status()
        return stats_resp.json().get("items", [])

    def _no_creds(self) -> str:
        prev = memory_store.get_agent(self.name)
        prev_subs = prev.get("data", {}).get("subscribers", 0)
        msg = (
            f"VIDEO PIPELINE\n"
            f"  [Demo mode — set YOUTUBE_API_KEY + YOUTUBE_CHANNEL_ID in .env]\n"
            f"  Last recorded subscribers: {prev_subs:,}"
        )
        memory_store.update_agent(self.name, msg)
        return msg
