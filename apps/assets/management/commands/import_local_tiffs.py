"""
Import local TIFF originals into the archive as fully-formed assets.

Place at: apps/assets/management/commands/import_local_tiffs.py
(create the management/ and commands/ folders with empty __init__.py files)

Usage:
    python manage.py import_local_tiffs --dir "/path/to/tiffs"
    python manage.py import_local_tiffs --dir ./tiffs --limit 10
    python manage.py import_local_tiffs --dir ./health_tiffs --category Health

What it does per file (e.g. "entertainment 2826-2881---34.tif"):
  1. category "Entertainment" parsed from the first word (or --category)
  2. TIFF opened with Pillow and rendered to FOUR JPEG variants, written
     through the "public_media"/"private_media" storage aliases — local
     disk in dev, Supabase Storage in production, same code either way:
       thumbnail  400px  watermarked  -> public   (listing grids)
       preview   1200px  watermarked  -> public   (detail page)
       web       1200px  clean        -> private  (purchasable)
       print     3000px  clean        -> private  (purchasable)
     the TIFF itself is copied as 'original' -> private
  3. DigitalAsset + AssetMetadata + AssetVariant rows created, PUBLISHED
  4. idempotent: re-running skips files already imported (by asset_number)

These are REAL originals, so public variants are always watermarked.
"""

import hashlib
import io
import re
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    raise CommandError("Pillow is required: pip install Pillow") from exc

from apps.assets.models import (
    AssetMetadata,
    AssetVariant,
    Category,
    DigitalAsset,
    Tag,
)

Image.MAX_IMAGE_PIXELS = None  # archive TIFFs can exceed Pillow's default cap

WATERMARK_TEXT = "PREVIEW"

RENDITIONS = [
    # (variant_name, max_px, watermarked, bucket, jpeg_quality)
    ("thumbnail", 400, True, "public", 80),
    ("preview", 1200, True, "public", 85),
    ("web", 1200, False, "private", 90),
    ("print", 3000, False, "private", 92),
]

# Filename → category + identifier, e.g.
#   "entertainment 2826-2881---34.tif"
#   "health 1751-1900-20_2-KNAPHT-3-09-001789-3.tif"
FILENAME_RE = re.compile(r"^(?P<category>[A-Za-z]+)[\s_]+(?P<ident>.+?)\.tiff?$", re.IGNORECASE)


def _watermark(img: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(img.width // 14, 18)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()
    step_x, step_y = font_size * 9, font_size * 4
    for y in range(0, img.height + step_y, step_y):
        offset = (y // step_y % 2) * (step_x // 2)
        for x in range(-step_x, img.width + step_x, step_x):
            draw.text((x + offset, y), WATERMARK_TEXT, font=font, fill=(255, 255, 255, 60))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


class Command(BaseCommand):
    help = "Convert local TIFF originals into published assets with 4 JPEG variants."

    def add_arguments(self, parser):
        parser.add_argument("--dir", required=True, help="Folder containing .tif files")
        parser.add_argument(
            "--category", default=None, help="Force a category name instead of parsing filenames"
        )
        parser.add_argument("--limit", type=int, default=None, help="Import at most N files")
        parser.add_argument(
            "--draft", action="store_true", help="Import as DRAFT instead of PUBLISHED"
        )

    # ------------------------------------------------------------------ #
    def handle(self, *args, **opts):
        src = Path(opts["dir"]).expanduser()
        if not src.is_dir():
            raise CommandError(f"Not a directory: {src}")

        files = sorted(p for p in src.iterdir() if p.suffix.lower() in (".tif", ".tiff"))
        if opts["limit"]:
            files = files[: opts["limit"]]
        if not files:
            raise CommandError(f"No .tif files found in {src}")

        self.stdout.write(f"Found {len(files)} TIFF file(s). Importing…")
        created = skipped = failed = 0

        for path in files:
            try:
                with transaction.atomic():
                    result = self._import_one(path, opts)
                if result == "created":
                    created += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {path.name}"))
                else:
                    skipped += 1
                    self.stdout.write(f"  – {path.name} (already imported)")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.stdout.write(self.style.ERROR(f"  ✗ {path.name}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created {created}, skipped {skipped}, failed {failed}.")
        )
        if created:
            self.stdout.write("Verify: GET /api/v1/assets — thumbnails should load directly.")

    # ------------------------------------------------------------------ #
    def _import_one(self, path: Path, opts) -> str:
        m = FILENAME_RE.match(path.name)
        cat_name = (opts["category"] or (m.group("category") if m else "Uncategorised")).title()
        ident = (m.group("ident") if m else path.stem).strip()

        # Idempotency key derived from the filename — stable across runs
        asset_number = f"LOCAL-{slugify(path.stem)[:40].upper()}"
        if DigitalAsset.objects.filter(asset_number=asset_number).exists():
            return "skipped"

        category, _ = Category.objects.get_or_create(
            name=cat_name, defaults={"slug": slugify(cat_name)}
        )

        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()

        asset = DigitalAsset.objects.create(
            asset_number=asset_number,
            title=f"{cat_name} archive record {ident}",
            description=f"Digitised {cat_name.lower()} photograph from the national archive. "
            f"Reference {ident}.",
            caption=f"{cat_name} collection, reference {ident}.",
            asset_type=DigitalAsset.AssetType.PHOTOGRAPH,
            status=DigitalAsset.Status.DRAFT if opts["draft"] else DigitalAsset.Status.PUBLISHED,
            visibility=DigitalAsset.Visibility.PUBLIC,
            category=category,
            photographer="Staff Photographer",
            photographer_credit="Kenya News Agency",
            source="KNA",
            copyright_holder="Kenya News Agency",
        )
        AssetMetadata.objects.create(
            asset=asset,
            keywords=f"{ident} {cat_name.lower()} archive kenya",
            country="Kenya",
            headline=asset.title[:255],
        )
        for tag_name in (cat_name.lower(), "archive", "kenya"):
            tag, _ = Tag.objects.get_or_create(
                name=tag_name, defaults={"slug": slugify(tag_name)[:50]}
            )
            asset.tags.add(tag)

        # ----- original TIFF → private storage -----
        original_rel = f"{asset_number}/original{path.suffix.lower()}"
        storages["private_media"].save(original_rel, ContentFile(content))
        AssetVariant.objects.create(
            asset=asset,
            variant_name="original",
            storage_path=original_rel,
            mime_type="image/tiff",
            file_size=len(content),
            checksum=checksum,
        )

        # ----- four JPEG renditions -----
        src_img = Image.open(io.BytesIO(content))
        if src_img.mode not in ("RGB", "L"):
            src_img = src_img.convert("RGB")

        for name, max_px, watermarked, bucket, quality in RENDITIONS:
            img = src_img.copy()
            img.thumbnail((max_px, max_px), Image.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")
            if watermarked:
                img = _watermark(img)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()

            rel = f"{asset_number}/{name}.jpg"
            storages[f"{bucket}_media"].save(rel, ContentFile(data))

            AssetVariant.objects.create(
                asset=asset,
                variant_name=name,
                storage_path=rel,
                mime_type="image/jpeg",
                file_size=len(data),
                checksum=hashlib.sha256(data).hexdigest(),
            )
        return "created"
