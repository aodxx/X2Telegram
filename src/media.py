from .models import MediaItem

def select_best_video(items: list[MediaItem]) -> MediaItem | None:
    videos=[i for i in items if i.kind == "video"]
    if not videos: return None
    return max(videos, key=lambda i: (i.bitrate or -1, (i.width or 0)*(i.height or 0)))
