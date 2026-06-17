import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("SELECT column_name, data_type, character_maximum_length FROM information_schema.columns WHERE table_name = 'contacts_contacttag' ORDER BY column_name;")
    for row in cursor.fetchall():
        print(row)
