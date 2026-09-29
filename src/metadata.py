from dataclasses import dataclass
from .models import MediaItem
from .urls import XPost

@dataclass
class Metadata:
    post: XPost
    media: list[MediaItem]

class MetadataProvider:
    def get(self, post: XPost) -> Metadata:
        raise NotImplementedError
