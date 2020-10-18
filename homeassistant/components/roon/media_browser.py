"""Support to interface with the Plex API."""
import logging

from homeassistant.components.media_player import BrowseMedia
from homeassistant.components.media_player.const import (
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_PLAYLIST,
    MEDIA_CLASS_TRACK,
)
from homeassistant.components.media_player.errors import BrowseError


class UnknownMediaType(BrowseError):
    """Unknown media type."""


EXCLUDE_ITEMS = {
    "Play Album",
    "Play Artist",
    "Play Playlist",
    "Play Composer",
    "Play Now",
    "Play From Here",
    "Queue",
    "Start Radio",
    "Add Next",
    "Play Radio",
    "Play Work",
    "Settings",
    "Search",
    "Search Tidal",
    "Search Qobuz",
}

# Maximum number of items to pull back from the API
ITEM_LIMIT = 3000

_LOGGER = logging.getLogger(__name__)


def browse_media(zone_id, roon_server, media_content_type=None, media_content_id=None):
    """Implement the websocket media browsing helper."""
    try:
        _LOGGER.debug("browse_media: %s: %s", media_content_type, media_content_id)
        if media_content_type in [None, "library"]:
            return library_payload(roon_server, zone_id, media_content_id)

    except UnknownMediaType as err:
        raise BrowseError(
            f"Media not found: {media_content_type} / {media_content_id}"
        ) from err


def item_payload(roon_server, item, list_image_id):
    """Create response payload for a single media item."""

    title = item.get("title")
    subtitle = item.get("subtitle")
    if subtitle is None:
        display_title = title
    else:
        display_title = f"{title} ({subtitle})"

    image_id = item.get("image_key") or list_image_id

    image = None
    if image_id:
        image = roon_server.roonapi.get_image(image_id)

    media_content_id = item.get("item_key")
    media_content_type = "library"

    hint = item.get("hint")
    if hint == "list":
        media_class = MEDIA_CLASS_DIRECTORY
        can_expand = True
    elif hint == "action_list":
        media_class = MEDIA_CLASS_PLAYLIST
        can_expand = False
    elif hint == "action":
        media_content_type = "track"
        media_class = MEDIA_CLASS_TRACK
        can_expand = False
    else:
        # Roon API says to treat unknown as a list
        media_class = MEDIA_CLASS_DIRECTORY
        can_expand = True
        _LOGGER.warning("Unknown hint %s - %s", title, hint)

    if title in EXCLUDE_ITEMS:
        return None

    payload = {
        "title": display_title,
        "media_class": media_class,
        "media_content_id": media_content_id,
        "media_content_type": media_content_type,
        "can_play": True,
        "can_expand": can_expand,
        "thumbnail": image,
    }

    return BrowseMedia(**payload)


def library_payload(roon_server, zone_id, media_content_id):
    """Create response payload for the library."""

    opts = {
        "hierarchy": "browse",
        "zone_or_output_id": zone_id,
        "count": ITEM_LIMIT,
    }

    # Roon starts browsing for a zone where it left off - so start from the top unless otherwise specified
    if media_content_id is None or media_content_id == "Explore":
        opts["pop_all"] = True
        content_id = "Explore"
    else:
        opts["item_key"] = media_content_id
        content_id = media_content_id

    result_header = roon_server.roonapi.browse_browse(opts)
    _LOGGER.debug("result_header %s", result_header)

    header = result_header["list"]
    title = header.get("title")

    subtitle = header.get("subtitle")
    if subtitle is None:
        list_title = title
    else:
        list_title = f"{title} ({subtitle})"

    total_count = header["count"]

    library_image_id = header.get("image_key")

    library_info = BrowseMedia(
        title=list_title,
        media_content_id=content_id,
        media_content_type="library",
        media_class=MEDIA_CLASS_DIRECTORY,
        can_play=False,
        can_expand=True,
        children=[],
    )

    result_detail = roon_server.roonapi.browse_load(opts)
    _LOGGER.debug("result_detail %s", result_detail)

    items = result_detail.get("items")
    count = len(items)

    if count < total_count:
        _LOGGER.error(
            "Exceeded limit of %d, loaded %d/%d", ITEM_LIMIT, count, total_count
        )

    for item in items:
        item = item_payload(roon_server, item, library_image_id)
        if not (item is None):
            library_info.children.append(item)

    return library_info
