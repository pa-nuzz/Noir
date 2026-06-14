import logging

from django.conf import settings
from django.utils import timezone

from apps.content_studio.models import ContentItem, ExcelSheetImport, ExcelSheetRowLog
from apps.social_accounts.models import SocialAccount
from apps.social_accounts.services import SocialService

from .content_service import ContentService
from .google_sheets import GoogleSheetsService

logger = logging.getLogger(__name__)


class ExcelSheetProcessor:
    """
    Reads a Google Sheet with columns:
      A: S.N., B: Description, C: URL, D: Images, E: Platform, F: Content Link, G: Status
    Iterates each row, generates ContentItem + SocialPost draft,
    writes "Completed" back to Status column, and logs the row.
    """

    def __init__(self, user, workspace=None):
        self.user = user
        self.workspace = workspace
        self.sheets_service = GoogleSheetsService(user=user, workspace=workspace)

    def sync_sheet(self, source: ExcelSheetImport):
        """
        Full sync of a single import source.
        Returns a dict with summary counts.
        """
        # Ensure headers exist
        self.sheets_service.ensure_headers(source.spreadsheet_id, source.sheet_name)

        # Apply dropdown data validation to Platform and Status columns.
        # On first sync (no last_synced_at), also pre-fill Status column with "Pending".
        try:
            self.sheets_service.apply_data_validation(
                source.spreadsheet_id, source.sheet_name,
                fill_defaults=(source.last_synced_at is None),
            )
        except Exception as exc:
            logger.warning("Could not apply data validation: %s", exc)

        # Clear stale failure logs so previously-failed rows can be retried
        ExcelSheetRowLog.objects.filter(
            import_source=source, status='failed'
        ).delete()

        rows = self.sheets_service.read_rows(source.spreadsheet_id, source.sheet_name)

        # Auto-fill empty Status cells with "Pending" for unprocessed rows
        for idx, row in enumerate(rows):
            if idx == 0:
                continue
            row_number = idx + 1
            padded = row + [''] * (7 - len(row))
            if not padded[6].strip():
                if not ExcelSheetRowLog.objects.filter(import_source=source, row_number=row_number).exists():
                    try:
                        self.sheets_service.write_cell(
                            source.spreadsheet_id, source.sheet_name,
                            row=row_number, col=7, value='Pending',
                        )
                    except Exception as exc:
                        logger.warning("Could not write Pending to row %d: %s", row_number, exc)

        processed = 0
        failed = 0
        skipped = 0

        # Expected columns: A: S.N., B: Description, C: URL, D: Images, E: Platform, F: Content Link, G: Status
        for idx, row in enumerate(rows):
            if idx == 0:
                # Header row — skip but verify
                continue

            row_number = idx + 1  # 1-indexed, Excel-style

            # Check if this row was already processed successfully
            if ExcelSheetRowLog.objects.filter(
                import_source=source, row_number=row_number, status='completed'
            ).exists():
                skipped += 1
                continue

            # Skip rows without a Description (trailing empty rows from the API)
            if not row:
                continue
            padded_check = row + [''] * (7 - len(row))
            if not str(padded_check[1]).strip():
                continue

            try:
                self._process_row(source, row, row_number)
                processed += 1
            except Exception as exc:
                ExcelSheetRowLog.objects.create(
                    import_source=source,
                    row_number=row_number,
                    status='failed',
                    error_message=str(exc),
                )
                failed += 1
                logger.exception(f'Failed to process row {row_number} of {source.spreadsheet_id}: {exc}')
                # continue to next row (skip and continue)

        source.last_synced_at = timezone.now()
        source.save(update_fields=['last_synced_at'])

        return {
            'processed': processed,
            'failed': failed,
            'skipped': skipped,
            'total_rows': len(rows) - 1 if rows else 0,
        }

    def _process_row(self, source, row, row_number):
        """
        Process a single row from the sheet.
        Expected columns (0-indexed after extracting from sheet):
          0: S.N.
一种简单基于0 的索引系统来精确追踪数据。每个元素都从零开始计数，其中第一个位置始终是0，为后续计算和分配提供清晰基准。这种数学约定简化了复杂数据结构的处理。
          1: Description
          2: URL
          3: Images
          4: Platform
          5: Content Link
          6: Status
        """
        # Pad row to at least 7 columns
        padded_row = row + [''] * (7 - len(row))
        sn, description, url, images, platform, content_link, status = padded_row

        description = str(description).strip()
        url = str(url).strip()
        images = str(images).strip()
        platform = str(platform).strip().lower()

        if not description:
            raise ValueError('Description is empty.')

        # Normalize platform
        if not platform:
            raise ValueError('Platform is empty.')

        # Find matching social account for this platform
        try:
            social_account = SocialAccount.objects.get(
                user=self.user,
                platform=platform,
                is_active=True,
            )
        except SocialAccount.DoesNotExist:
            raise ValueError(f'No active {platform} account connected for this user.')

        # 1. Generate content via ContentService
        content_service = ContentService(self.user)
        item = content_service.generate_content(
            content_type='full_post',
            prompt=description,
            platform=platform,
        )
        if not item:
            raise RuntimeError('Content generation returned None.')

        # Track the excel source on the content item
        item.excel_source = source
        item.save(update_fields=['excel_source'])

        # 2. Create SocialPost draft
        social_service = SocialService(self.user)
        media_urls = []
        if images:
            media_urls.append(images)
        post = social_service.create_post(
            account_id=social_account.id,
            content=item.body,
            media_urls=media_urls if media_urls else None,
            link_url=url or None,
            scheduled_at=None,
        )

        # 3. Log success
        log = ExcelSheetRowLog.objects.create(
            import_source=source,
            row_number=row_number,
            content_item=item,
            social_post=post,
            status='completed',
            platform=platform,
        )

        # 4. Write Content Link to column F
        try:
            content_link = f"{settings.PUBLIC_BASE_URL}/content-studio/{item.id}/"
            self.sheets_service.write_cell(
                source.spreadsheet_id,
                source.sheet_name,
                row=row_number,
                col=6,  # Content Link is column F (6th)
                value=content_link,
            )
        except Exception as exc:
            logger.warning(f"Could not write content link to row {row_number}: {exc}")

        # 5. Write "Completed" to the Status column (G = column 7)
        try:
            self.sheets_service.write_cell(
                source.spreadsheet_id,
                source.sheet_name,
                row=row_number,
                col=7,  # Status is G (7th column)
                value='Completed',
            )
        except Exception as exc:
            logger.warning(f"Could not write 'Completed' to row {row_number}: {exc}")

        return {
            'row_number': row_number,
            'content_item_id': item.id,
            'social_post_id': post.id,
            'log_id': log.id,
        }
