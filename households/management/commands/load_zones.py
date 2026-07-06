from django.core.management.base import BaseCommand
from accounts.models import Barangay
from households.models import Zone

class Command(BaseCommand):
    help = 'Load Barangays and their Zones'

    def handle(self, *args, **kwargs):
        zones_data = {
            "Becuran": 6,
            "Dila-Dila": 7,
            "San Matias": 7,
            "San Vicente": 4,
            "Santa Monica": 4,
            "San Agustin": 3,
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
            
            # 1. Create or get required zones
            for i in range(1, count + 1):
                Zone.objects.get_or_create(
                    barangay=barangay,
                    name=f"Zone {i}"
                )
                
            # 2. Check for any extra zones that need to be safely removed
            existing_zones = Zone.objects.filter(barangay=barangay)
            for zone in existing_zones:
                if zone.name.startswith("Zone "):
                    try:
                        zone_num = int(zone.name.split(" ")[1])
                        if zone_num > count:
                            household_count = zone.households.count()
                            if household_count > 0:
                                self.stdout.write(
                                    self.style.ERROR(
                                        f"Cannot remove {barangay.name} {zone.name}: {household_count} household(s) linked. Manual review required."
                                    )
                                )
                            else:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"Removing empty {barangay.name} {zone.name}..."
                                    )
                                )
                                zone.delete()
                    except ValueError:
                        pass

        self.stdout.write(self.style.SUCCESS("Barangays and Zones loaded successfully"))
