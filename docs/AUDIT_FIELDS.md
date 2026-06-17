# Audit Fields Standard

Every model in this project inherits from `AuditMixin` (`core.models.AuditMixin`) which provides 8 standard audit fields for tracking record creation and modification.

## Field Definitions

| Field | Type | Purpose | Auto-populated |
|-------|------|---------|----------------|
| `postby` | FK → User (nullable) | Who created the record | Auto from middleware |
| `postdatead` | DateTimeField | When created (AD / Gregorian) | Auto on creation |
| `postdatebs` | CharField(10) | When created (BS / Nepali) | Auto-computed from postdatead |
| `posttime` | TimeField | When created (time component) | Auto on creation |
| `modifyby` | FK → User (nullable) | Who last modified the record | Auto from middleware |
| `modifydatead` | DateTimeField (nullable) | When last modified (AD) | Auto on update |
| `modifydatebs` | CharField(10) (nullable) | When last modified (BS) | Auto-computed from modifydatead |
| `modifytime` | TimeField (nullable) | When last modified (time) | Auto on update |

## How It Works

### Auto-population Flow

1. `AuditContextMiddleware` (`apps/audit/middleware.py`) captures the authenticated user from each request into `threading._audit_user`.
2. `AuditMixin.save()` reads `threading._audit_user` to set `postby` (on creation) and `modifyby` (on every save).
3. BS (Bikram Sambat / Nepali) dates are auto-computed from AD dates using the `nepali_datetime` library.

### Creation (first save)
- `postdatead` = current timestamp
- `posttime` = current time
- `postdatebs` = computed from `postdatead`
- `postby` = current request user (via middleware)
- `modify*` fields remain null

### Update (subsequent saves)
- `modifydatead` = current timestamp
- `modifytime` = current time
- `modifydatebs` = computed from `modifydatead`
- `modifyby` = current request user (via middleware)
- `post*` fields remain unchanged

## BS Date Conversion

BS dates are computed using the `nepali-datetime` Python library.

**Key functions** (`core/utils/nepali_calendar.py`):
- `ad_to_bs(ad_date)` — Converts AD date/datetime to BS string (YYYY-MM-DD)
- `bs_to_ad(bs_str)` — Converts BS string to AD date object
- `current_bs_date()` — Returns today's date in BS
- `ad_to_bs_datetime_string(ad_datetime)` — Full datetime string conversion

## Adding AuditMixin to a New Model

```python
from django.conf import settings
from django.db import models
from core.models import AuditMixin

class MyNewModel(AuditMixin):
    name = models.CharField(max_length=255)
    
    class Meta:
        ordering = ['-postdatead']
```

## Migration Guide

### For existing data:
1. Run `python manage.py migrate <app_name>` — new audit columns are added with `null`/default values
2. Run the backfill command to populate existing records:
   ```bash
   python manage.py backfill_audit_fields
   ```

### Dependencies
- `nepali-datetime` must be installed:
  ```bash
  pip install nepali-datetime
  ```

## Notes

- Existing `created_at` / `updated_at` fields are preserved for backward compatibility.
- Models with existing `created_by` FK fields (e.g., `notifications.Notification`) retain them alongside the new `postby` field.
- `postby` and `modifyby` use `related_name='+'` to avoid reverse relation conflicts across models.
