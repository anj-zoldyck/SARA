from django.core.management.base import BaseCommand
from accounts.models import Barangay, User
from households.models import Zone, Household

class Command(BaseCommand):
    help = 'Load Barangays and their Zones'

    def handle(self, *args, **kwargs):
        zones_data = {
            "Becuran": 6,
            "Dila-Dila": 7,
            "San Matias": 7,
            "Santa Monica": 4,
            "San Agustin": 3,
            "San Jose (Poblacion)": 7,
            "San Juan": 7,
            "San Isidro": 3,
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

        # Merge San Juan Macaba + San Juan Cacutud into San Juan
        old_barangays = ["San Juan Macaba", "San Juan Cacutud"]
        for old_name in old_barangays:
            try:
                old_barangay = Barangay.objects.get(name=old_name)
                household_count = Household.objects.filter(zone__barangay=old_barangay).count()
                user_count = User.objects.filter(barangay=old_barangay).count()
                
                self.stdout.write(
                    f"Checking {old_name}: {household_count} household(s), {user_count} user(s)"
                )
                
                if household_count > 0 or user_count > 0:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Cannot delete {old_name}: {household_count} household(s) and/or {user_count} user(s) linked. Manual review required."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Deleting empty barangay {old_name} and its zones..."
                        )
                    )
                    Zone.objects.filter(barangay=old_barangay).delete()
                    old_barangay.delete()
            except Barangay.DoesNotExist:
                self.stdout.write(
                    f"Barangay '{old_name}' does not exist (already cleaned up)."
                )

        # Rename San Vicente zones to street names
        try:
            san_vicente = Barangay.objects.get(name="San Vicente")
            street_names = {
                "Zone 1": "Chapel Street",
                "Zone 2": "Salaria Street",
                "Zone 3": "Gosioco Street",
                "Zone 4": "Pigulut Street"
            }
            for old_name, new_name in street_names.items():
                zone = Zone.objects.filter(barangay=san_vicente, name=old_name).first()
                if zone:
                    self.stdout.write(
                        f"Renaming San Vicente {old_name} to {new_name}..."
                    )
                    zone.name = new_name
                    zone.save()
        except Barangay.DoesNotExist:
            self.stdout.write(
                "Barangay 'San Vicente' does not exist (will be created with custom names)."
            )

        for barangay_name, count in zones_data.items():
            # Skip San Vicente - it uses custom street names instead of numbered zones
            if barangay_name == "San Vicente":
                continue
                
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

        # Create San Vicente with custom street names if it doesn't exist
        try:
            san_vicente = Barangay.objects.get(name="San Vicente")
        except Barangay.DoesNotExist:
            san_vicente = Barangay.objects.create(name="San Vicente")
            street_names = [
                "Chapel Street",
                "Salaria Street",
                "Gosioco Street",
                "Pigulut Street"
            ]
            for street_name in street_names:
                Zone.objects.get_or_create(
                    barangay=san_vicente,
                    name=street_name
                )
            self.stdout.write(
                self.style.SUCCESS("Created San Vicente with custom street names")
            )

        self.stdout.write(self.style.SUCCESS("Barangays and Zones loaded successfully"))
