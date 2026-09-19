from django.core.management.base import BaseCommand
from distribution.models import DistributionVenue
from accounts.models import Barangay


class Command(BaseCommand):
    help = 'Rename barangay hall venues from "{barangay} Hall" to "{barangay} Barangay Hall" pattern'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be renamed without actually making changes'
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        # Get all barangay names from the JSON fixture to identify seeded venues
        import json
        import os
        from django.conf import settings
        
        fixture_path = os.path.join(settings.BASE_DIR, 'distribution/fixtures/barangay_halls.json')
        
        if not os.path.exists(fixture_path):
            self.stdout.write(self.style.ERROR(f'Fixture file not found: {fixture_path}'))
            return
        
        with open(fixture_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        seeded_barangay_names = [entry['barangay_name'] for entry in data]
        
        # Find venues matching the old pattern for seeded barangays
        venues_to_rename = []
        
        for barangay_name in seeded_barangay_names:
            old_name = f"{barangay_name} Hall"
            new_name = f"{barangay_name} Barangay Hall"
            
            # Find venue with old name pattern
            venue = DistributionVenue.objects.filter(
                name=old_name
            ).first()
            
            if venue:
                venues_to_rename.append({
                    'venue': venue,
                    'old_name': old_name,
                    'new_name': new_name,
                    'barangay_name': barangay_name
                })
        
        if not venues_to_rename:
            self.stdout.write(self.style.SUCCESS('No venues found matching the old naming pattern.'))
            return
        
        # Report what will be done
        self.stdout.write('\n' + '='*60)
        self.stdout.write(f'Found {len(venues_to_rename)} venues to rename:')
        self.stdout.write('='*60)
        
        for item in venues_to_rename:
            self.stdout.write(f'  "{item["old_name"]}" -> "{item["new_name"]}"')
        
        self.stdout.write('='*60)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes made.'))
            self.stdout.write('Run without --dry-run to apply these changes.')
            return
        
        # Confirm before proceeding
        response = input('\nProceed with renaming? (yes/no): ')
        if response.lower() != 'yes':
            self.stdout.write(self.style.WARNING('Operation cancelled.'))
            return
        
        # Apply renames
        renamed_count = 0
        for item in venues_to_rename:
            venue = item['venue']
            venue.name = item['new_name']
            venue.save()
            self.stdout.write(self.style.SUCCESS(f'Renamed: {item["old_name"]} -> {item["new_name"]}'))
            renamed_count += 1
        
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'Successfully renamed {renamed_count} venues.'))
        self.stdout.write('='*60)
