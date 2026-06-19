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
            "San Vicente": 5,
            "Santa Monica": 4,
            "San Agustin": 3,
            "San Jose": 5,
            "San Juan Macaba": 3,
            "San Juan Cacutud": 3,
            "San Isidro": 4,
            "San Basilio": 8
        }

        for barangay_name, count in zones_data.items():
            barangay, _ = Barangay.objects.get_or_create(name=barangay_name)
            for i in range(1, count + 1):
                Zone.objects.get_or_create(
                    barangay=barangay,
                    name=f"Zone {i}"
                )

        self.stdout.write(self.style.SUCCESS("Barangays and Zones loaded successfully"))
