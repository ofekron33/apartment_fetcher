import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Dizengoff Square, Tel Aviv
REFERENCE_LAT = 32.0775
REFERENCE_LON = 34.7744


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points using haversine formula."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _relative_time(iso_str: str) -> str:
    """Convert an ISO datetime string to a human-readable relative time."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        days = hours // 24
        if days < 30:
            return f"{days} day{'s' if days != 1 else ''} ago"
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    except (ValueError, TypeError):
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


@dataclass
class Listing:
    id: str
    source: str = "yad2"
    price: Optional[int] = None
    rooms: Optional[float] = None
    floor: Optional[int] = None
    elevator: Optional[bool] = None
    parking: Optional[bool] = None
    address: str = ""
    neighborhood: str = ""
    size_sqm: Optional[int] = None
    link: str = ""
    order_id: Optional[int] = None
    description: Optional[str] = None
    entrance_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    ends_at: Optional[str] = None
    rebounced_at: Optional[str] = None
    facebook_url: Optional[str] = None
    is_realtor: Optional[bool] = None
    author_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    distance_km: Optional[float] = None

    def summary(self) -> str:
        parts = [
            f"Price: {self.price:,} ILS" if self.price else "Price: N/A",
            f"Address: {self.address}" if self.address else "",
        ]
        if self.distance_km is not None:
            parts.append(f"Distance: {self.distance_km:.1f} km from Dizengoff Sq.")
        # Detail fields — only show if available (4kirot doesn't have these)
        if self.rooms is not None:
            parts.append(f"Rooms: {self.rooms}")
        if self.floor is not None:
            parts.append(f"Floor: {self.floor}")
        if self.size_sqm is not None:
            parts.append(f"Size: {self.size_sqm} sqm")
        if self.elevator is not None:
            parts.append(f"Elevator: {'Yes' if self.elevator else 'No'}")
        if self.parking is not None:
            parts.append(f"Parking: {'Yes' if self.parking else 'No'}")
        if self.neighborhood:
            parts.append(f"Neighborhood: {self.neighborhood}")
        if self.entrance_date:
            parts.append(f"Entrance: {self.entrance_date[:10]}")
        if self.created_at:
            parts.append(f"Posted: {_relative_time(self.created_at)}")
        if self.updated_at:
            parts.append(f"Updated: {self.updated_at[:10]}")
        if self.ends_at:
            parts.append(f"Expires: {self.ends_at[:10]}")
        if self.rebounced_at:
            parts.append(f"Last bump: {self.rebounced_at[:10]}")
        if self.is_realtor:
            parts.append("Realtor: Yes")
        if self.author_name:
            parts.append(f"Posted by: {self.author_name}")
        if self.description:
            parts.append(f"\n{self.description}")
        return "\n".join(p for p in parts if p)


@dataclass
class ScoredListing:
    listing: Listing
    score: int = 0
    breakdown: dict = field(default_factory=dict)

    def format_message(self, use_emoji: bool = True) -> str:
        house = "\U0001f3e0" if use_emoji else "[*]"
        link_icon = "\U0001f517" if use_emoji else "Link:"
        fb_icon = "\U0001f4ac" if use_emoji else "FB:"
        source_label = self.listing.source.upper()
        lines = [
            f"{house} New Apartment [{source_label}] (Score: {self.score})",
            "",
            self.listing.summary(),
            "",
            "Score breakdown:",
        ]
        for reason, pts in self.breakdown.items():
            lines.append(f"  {reason}: +{pts}")
        if self.listing.link:
            lines.append(f"\n{link_icon} {self.listing.link}")
        if self.listing.facebook_url:
            lines.append(f"{fb_icon} Facebook post: {self.listing.facebook_url}")
        return "\n".join(lines)
