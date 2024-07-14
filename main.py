import asyncio
import os
import time
from typing import Any
from uuid import uuid4

import httpx
import uvicorn
import yt_dlp as youtube_dl

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from youtubesearchpython.__future__ import VideosSearch

app = FastAPI(redoc_url=None)
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 OPR/111.0.0.0"
cache = {}


async def get_mp4(playback: str) -> bytes:
    async with httpx.AsyncClient() as client:
        res = await client.get(playback, headers={"User-Agent": user_agent})
        res.raise_for_status()
        return res.content


def make_cache(q: str, video: bytes):
    os.makedirs(".video-cache/", exist_ok=True)

    here = str(uuid4())
    cache[q] = {"i": here, "t": time.time()}

    with open(f".video-cache/{here}", "wb") as f:
        f.write(video)


def tick():
    for k, v in list(cache.items()):
        if time.time() - v["t"] > 60 * 60 * 2:
            os.remove(f".video-cache/{v['i']}")
            del cache[k]


@app.get("/api/v2/youtube")
async def api_v2_youtube_mp4(q: str):
    tick()

    async def youtube_search(query: str):
        if query.startswith("id="):
            return "https://youtube.com/watch?v=" + query

        search = VideosSearch(query, limit=1)
        result = await search.next()
        return "https://youtube.com/watch?v=" + result["result"][0]["id"]

    _accepted_urls = (
        "https://youtube.com/watch?v=",
        "https://www.youtube.com/watch?v=",
        "https://youtu.be/",
    )
    is_youtube_url = q.startswith(_accepted_urls)
    try:
        url = q if is_youtube_url else await youtube_search(q)
    except IndexError:
        return JSONResponse({"message": f"Cannot find any video for query {q!r}"}, 500)

    def extract_info(url: str) -> dict[str, Any]:
        ydl_opts = {
            "format": "mp4/bestvedio/best",
            "noplaylist": "True",
            "dump_single_json": "True",
            "extract_flat": "True",
            "quiet": "True",
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        return info  # type: ignore

    if q in cache:
        loc = f".video-cache/{cache[q]['i']}"
        with open(loc, "rb") as f:
            vid = f.read()

    else:
        loop = asyncio.get_event_loop()

        info = await loop.run_in_executor(None, extract_info, url)
        url = info.get("url")

        if not url:
            return JSONResponse(
                {"message": "Error: Cannot retrieve playback URL. Maybe try again?"},
                500,
            )

        vid = await get_mp4(url)
        make_cache(q, vid)

    return Response(vid, media_type="video/mp4")


if __name__ == "main":
    uvicorn.run(app, port=8000)
