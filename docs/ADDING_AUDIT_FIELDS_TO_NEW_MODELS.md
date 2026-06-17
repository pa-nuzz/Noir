# Adding Audit Fields to a New Model

Every model in this project **MUST** inherit from `AuditMixin` to ensure consistent audit tracking across the application.

## Standard Template

```python
from django.conf import settings
from django.db import models
from core.models import AuditMixin

class YourModel(AuditMixin):
    # Your fields here
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ['-postdatead']

    def __str__(self):
        return self.name
```

## Migration

After defining the model:

```bash
python manage.py makemigrations <your_app>
python manage.py migrate <your_app>
```

## AuditMixin provides these fields automatically:

| Field | Purpose | Auto-population |
|-------|---------|----------------|
| `postby` → User | Who created it | From middleware |
| `postdatead` | Creation date (AD) | Auto on creation |
| `postdatebs` | Creation date (BS) | Computed from postdatead |
| `posttime` | Creation time | Auto on creation |
| `modifyby` → User | Who modified it | From middleware |
| `modifydatead` | Modification date (AD) | Auto on every save |
| `modifydatebs` | Modification date (BS) | Computed from modifydatead |
| `modifytime` | Modification time | Auto on every save |

## Important Notes

1. **Do NOT add separate `created_at` or `updated_at` fields** — AuditMixin already provides `postdatead`/`modifydatead` which serve the same purpose.
2. **Do NOT add separate `created_by` or `updated_by` fields** — Use `postby`/`modifyby` instead.
3. **Use `postdatead` for ordering** instead of `created_at`.
   - Correct: `ordering = ['-postdatead']`
   - Incorrect: `ordering = ['-created_at']`
4. If the model overrides `save()`, ensure it calls `super().save()` so the audit fields are set properly.

## Example with Custom save()

```python
class YourModel(AuditMixin):
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        # Custom logic
        if self.name:
            self.name = self.name.strip()
        # AuditMixin.save() will handle audit fields automatically
        super().save(*args, **kwargs)
```
