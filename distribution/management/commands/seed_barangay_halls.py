from django.core.management.base import BaseCommand
from django.conf import settings
import json
import os
from decimal import Decimal, InvalidOperation
from distribution.models import DistributionVenue
from accounts.models import Barangay


class Command(BaseCommand):
    help = 'Seed barangay halls as DistributionVenue records from a JSON fixture file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='distribution/fixtures/barangay_halls.json',
            help='Path to the JSON fixture file containing barangay hall coordinates'
        )

    def handle(self, *args, **options):
        fixture_path = options['file']
        
        # Resolve path relative to project root if not absolute
        if not os.path.isabs(fixture_path):
            fixture_path = os.path.join(settings.BASE_DIR, fixture_path)
        
        if not os.path.exists(fixture_path):
            self.stdout.write(self.style.ERROR(f'Fixture file not found: {fixture_path}'))
            return
        
        self.stdout.write(f'Reading fixture file: {fixture_path}')
        
        try:
            with open(fixture_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'Invalid JSON in fixture file: {e}'))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error reading fixture file: {e}'))
            return
        
        created_count = 0
        skipped_count = 0
        not_found_count = 0
        
        for entry in data:
            barangay_name = entry.get('barangay_name')
            latitude = entry.get('latitude')
            longitude = entry.get('longitude')
            
            if not barangay_name or latitude is None or longitude is None:
                self.stdout.write(self.style.WARNING(f'Skipping invalid entry: {entry}'))
                skipped_count += 1
                continue
            
            # Look up the barangay
            try:
                barangay = Barangay.objects.get(name=barangay_name)
            except Barangay.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'Barangay not found in database: {barangay_name}'))
                not_found_count += 1
                continue
            
            # Check for duplicate venue for this barangay
            venue_name = f"{barangay_name} Barangay Hall"
            existing_venue = DistributionVenue.objects.filter(
                barangay=barangay,
                name=venue_name
            ).first()
            
            if existing_venue:
                self.stdout.write(self.style.WARNING(f'Venue already exists for {barangay_name}: {venue_name}'))
                skipped_count += 1
                continue
            
            # Create the venue
            try:
                lat_decimal = Decimal(str(latitude))
                lng_decimal = Decimal(str(longitude))
            except (InvalidOperation, ValueError) as e:
                self.stdout.write(self.style.ERROR(f'Invalid coordinates for {barangay_name}: {e}'))
                skipped_count += 1
                continue
            
            venue = DistributionVenue.objects.create(
                name=venue_name,
                latitude=lat_decimal,
                longitude=lng_decimal,
                barangay=barangay,
                is_active=True
            )
            
            self.stdout.write(self.style.SUCCESS(f'Created venue: {venue_name} (Lat: {lat_decimal}, Lng: {lng_decimal})'))
            created_count += 1
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(f'Total entries processed: {len(data)}')
        self.stdout.write(self.style.SUCCESS(f'Venues created: {created_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped (already exists): {skipped_count}'))
        self.stdout.write(self.style.WARNING(f'Barangays not found: {not_found_count}'))
        self.stdout.write('='*50)
