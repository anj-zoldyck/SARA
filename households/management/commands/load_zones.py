from django.core.management.base import BaseCommand
from accounts.models import Barangay
from households.models import Zone

class Command(BaseCommand):
    help = 'Load Barangays and their Zones'

    def handle(self, *args, **kwargs):
        zones_data = {
            "Becuran": 6,
            "Dila-Dila": 7,
            "San Matias": 4,
            "San Vicente": 4,
            "Santa Monica": 4,
            "San Agustin": 4,
            "San Jose (Poblacion)": 7,
            "San Juan Macaba": 3,
            "San Juan Cacutud": 3,
            "San Isidro": 4,
            "San Basilio": 8
        }

        # Handle San Jose rename if it exists under old name
        try:
            old_san_jose = Barangay.objects.get(name="San Jose")
            self.stdout.write(
                self.style.WARNING(
                    f'Found existing "San Jose" barangay. Renaming to "San Jose (Poblacion)"'
                )
            )
            old_san_jose.name = "San Jose (Poblacion)"
            old_san_jose.save()
        except Barangay.DoesNotExist:
            pass

        for barangay_name, count in zones_data.items():
            barangay, _ = Barangay.objects.get_or_create(name=barangay_name)
            for i in range(1, count + 1):
                Zone.objects.get_or_create(
                    barangay=barangay,
                    name=f"Zone {i}"
                )

        self.stdout.write(self.style.SUCCESS("Barangays and Zones loaded successfully"))
