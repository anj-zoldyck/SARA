import os
import sys
import django

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SARA.settings')
django.setup()

from programs.models import Program

programs = Program.objects.all().order_by('name')
print("Current Programs in database:")
print("-" * 50)
for p in programs:
    print(f"{p.id}: {p.name} (active={p.is_active})")
